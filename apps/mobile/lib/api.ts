import Constants from "expo-constants";

function candidates(): string[] {
  const extra = Constants.expoConfig?.extra ?? {};
  const list = [...((extra.apiCandidates as string[] | undefined) ?? [])];
  const single = extra.apiUrl as string | undefined;
  if (single) list.push(single);
  // In Expo Go the dev machine's address is discoverable from the dev-server host
  const devHost = Constants.expoConfig?.hostUri?.split(":")[0];
  if (devHost) list.push(`http://${devHost}:8040`);
  if (list.length === 0) list.push("http://localhost:8040");
  return [...new Set(list)];
}

// Active base: first candidate until a health probe picks the reachable one
// (Tailscale first → works from any network; Wi-Fi LAN as fallback).
let activeBase: string = candidates()[0];
export const getBase = (): string => activeBase;

let token: string | null = null;
export const setToken = (t: string | null) => (token = t);

// registered by the store: fired on any 401 so an expired session routes to sign-in
// instead of silently blanking every screen
let onUnauthorized: (() => void) | null = null;
export const setOnUnauthorized = (cb: () => void) => (onUnauthorized = cb);

const TIMEOUT_MS = 12000;
// generation endpoints (LLM work) legitimately run for tens of seconds
const SLOW_MS = 90000;
const SLOW_PATTERNS = [/\/lesson/, /\/video$/, /\/drill$/, /\/session\/start$/, /\/open$/,
                       /\/mocks\/start$/, /enrich-explanations/, /\/diagnostic\/start$/,
                       /\/flashcards/, /\/starter-pack$/];

async function req<T>(method: string, path: string, body?: unknown, form?: FormData,
                      retried = false): Promise<T> {
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const slow = SLOW_PATTERNS.some((p) => p.test(path));
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), slow ? SLOW_MS : TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${activeBase}${path}`, {
      method,
      headers,
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal: ctrl.signal,
    });
  } catch (e) {
    clearTimeout(timer);
    // network flap (e.g. Tailscale slept): re-probe all candidates and retry once —
    // uploads excluded (FormData bodies can't be safely replayed here)
    if (!retried && !form) {
      const healthy = await healthCheck();
      if (healthy) return req<T>(method, path, body, form, true);
    }
    const aborted = e instanceof Error && e.name === "AbortError";
    throw new Error(
      aborted
        ? `Server timed out (${activeBase}). Is the Ace API machine on and reachable?`
        : `Can't reach the server at ${activeBase}. Check Tailscale on this phone, or join the API machine's Wi-Fi.`,
    );
  } finally {
    clearTimeout(timer);
  }
  if (res.status === 401 && token) {
    onUnauthorized?.();
    throw new Error("Your session expired — please sign in again.");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text.slice(0, 200)}`);
  }
  return res.json() as Promise<T>;
}

async function probe(base: string): Promise<boolean> {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 4000);
    const res = await fetch(`${base}/health`, { signal: ctrl.signal });
    clearTimeout(timer);
    return res.ok;
  } catch {
    return false;
  }
}

/** Probe candidates in order (Tailscale → LAN → dev host); lock onto the first that answers. */
export async function healthCheck(): Promise<boolean> {
  for (const base of candidates()) {
    if (await probe(base)) {
      activeBase = base;
      return true;
    }
  }
  return false;
}

// ---- types (mirror API responses) ----
export type Question = {
  id: number;
  format: "mcq" | "tf" | "gap" | "match" | "numeric";
  cognitive_level: string;
  payload: {
    stem?: string; options?: string[]; statement?: string; text_with_gap?: string;
    left?: string[]; right?: string[]; unit?: string;
  };
};
export type Reveal = {
  correct: boolean; explanation: string; citations: { chunk_id: number }[];
  correct_index?: number; answer?: boolean | number; answers?: string[]; pairs?: number[][];
  option_notes?: Record<string, string>;
};
export type PlanItem = {
  id: number; day: string; kind: "learn" | "review" | "mock" | "taper";
  est_minutes: number; status: string; topic_codes?: string[] | null;
};
export type SessionStart = {
  session_id: number;
  lesson: { id: number; kind: string; body: string } | null;
  video: { id: number; youtube_id: string; title: string } | null;
  questions: Question[];
  already_answered?: number;
};
export type Readiness = {
  composite: number;
  signals: Record<string, number>;
  topics: { code: string; title: string; mastery: number; weight: number; attempts: number }[];
  elements: { code: string; title: string; mastery: number; weight: number;
              attempts: number }[];
  per_format: Record<string, { accuracy: number; n: number }>;
};
export type TopicNode = {
  id: number; parent_id: number | null; code: string; title: string; weight: number;
  cognitive_levels: string[]; source: string; mastery: number | null; attempts: number;
  question_count: number;
};
export type Sources = {
  preloaded: { name: string; provenance: string; topics: number; active_questions: number;
               removed_questions: number } | null;
  documents: { id: number; filename: string; kind: string; parse_status: string;
               page_count: number | null; chunks: number }[];
};
export type TopicDetail = {
  id: number; code: string; title: string; cognitive_levels: string[]; weight: number;
  mastery: number | null; attempts: number; question_count: number;
  lesson: { id: number; body: string } | null;
  video: { id: number; youtube_id: string; title: string } | null;
};
export type Gamify = {
  xp: number; level: number;
  streak: { current: number; best: number };
  badges: { key: string; label: string; awarded_at: string }[];
};

export const api = {
  requestOtp: (email: string) =>
    req<{ sent: boolean; dev_code?: string }>("POST", "/auth/otp", { email }),
  verifyOtp: (email: string, code: string) =>
    req<{ token: string; user: { id: number; email: string; selected_model: string } }>(
      "POST", "/auth/verify", { email, code }),

  createExam: (name: string, exam_date: string, weekly_hours: number) =>
    req<{ exam_id: number; accelerator: string | null }>("POST", "/exams",
      { name, exam_date, weekly_hours }),
  listExams: () =>
    req<{ exams: { id: number; name_raw: string; status: string; exam_date: string | null }[] }>(
      "GET", "/exams"),
  patchExam: (examId: number, patch: { exam_date?: string; weekly_hours?: number }) =>
    req<{ updated: boolean; plan_rebuilt: boolean }>("PATCH", `/exams/${examId}`, patch),
  topicTree: (examId: number) =>
    req<{ topics: TopicNode[] }>("GET", `/exams/${examId}/topic-tree`),
  sources: (examId: number) =>
    req<Sources>("GET", `/exams/${examId}/sources`),
  removePreloaded: (examId: number) =>
    req<{ removed: number }>("DELETE", `/exams/${examId}/preloaded-questions`),
  restorePreloaded: (examId: number) =>
    req<{ restored: number }>("POST", `/exams/${examId}/preloaded-questions/restore`),
  deleteDocument: (examId: number, docId: number) =>
    req<{ deleted: boolean; chunks_removed: number; generated_questions_removed: number }>(
      "DELETE", `/exams/${examId}/documents/${docId}`),
  topicDetail: (topicId: number) =>
    req<TopicDetail>("GET", `/topics/${topicId}`),
  topicLesson: (topicId: number, rewrite = false) =>
    req<{ lesson_id: number; body: string; created: boolean }>(
      "POST", `/topics/${topicId}/lesson${rewrite ? "?rewrite=true" : ""}`),
  topicVideo: (topicId: number) =>
    req<{ video: { id: number; youtube_id: string; title: string } | null;
          created: boolean; note?: string }>("POST", `/topics/${topicId}/video`),
  topicDrill: (topicId: number) =>
    req<{ session_id: number; count: number }>("POST", `/topics/${topicId}/drill`),
  openSession: (sessionId: number) =>
    req<SessionStart>("POST", `/sessions/${sessionId}/open`),
  getExam: (id: number) =>
    req<{ id: number; name_raw: string; status: string; exam_date: string | null;
          weekly_hours: number; accelerator_id: number | null;
          counts: { topics: number; chunks: number; questions: number };
          documents: { id: number; filename: string; kind: string; parse_status: string;
                       page_count: number | null }[] }>(
      "GET", `/exams/${id}`),
  uploadDocument: (examId: number, file: { uri: string; name: string; mimeType?: string }) => {
    const form = new FormData();
    form.append("file", { uri: file.uri, name: file.name, type: file.mimeType ?? "application/pdf" } as unknown as Blob);
    return req<{ document_id: number }>("POST", `/exams/${examId}/documents`, undefined, form);
  },
  ingestionStatus: (examId: number) =>
    req<{ exam_status: string; documents: { filename: string; kind: string; parse_status: string }[] }>(
      "GET", `/exams/${examId}/ingestion-status`),
  confirmSetup: (examId: number) => req<{ status: string }>("POST", `/exams/${examId}/confirm`),

  diagnosticStart: (examId: number) =>
    req<{ session_id: number; question_ids: number[]; count: number;
          resumed?: boolean; already_answered?: number }>(
      "POST", `/exams/${examId}/diagnostic/start`),
  diagnosticComplete: (examId: number, sessionId: number) =>
    req<{ result: { accuracy: number }; plan: { plan_id: number } }>(
      "POST", `/exams/${examId}/diagnostic/${sessionId}/complete`),

  getPlan: (examId: number) =>
    req<{ plan_id: number; rationale: string; completed_sessions: number; items: PlanItem[] }>(
      "GET", `/exams/${examId}/plan`),
  todayItem: (examId: number) =>
    req<{ item: PlanItem | null; session: { id: number } | null }>(
      "GET", `/exams/${examId}/plan/today`),
  nextItem: (examId: number) =>
    req<{ item: PlanItem | null }>("GET", `/exams/${examId}/plan/next`),
  rebuildPlan: (examId: number) => req<{ plan_id: number }>("POST", `/exams/${examId}/plan/rebuild`),

  startSession: (planItemId: number) =>
    req<SessionStart>("POST", `/plan-items/${planItemId}/session/start`),
  submitAttempt: (a: { exam_id: number; question_id: number; session_id?: number; mock_id?: number;
                       answer: Record<string, unknown>; confidence?: string; ms_taken?: number }) =>
    req<Reveal>("POST", "/attempts", a),
  completeSession: (sessionId: number) =>
    req<{ completed: boolean; streak: { current: number }; answered: number; correct: number }>(
      "POST", `/sessions/${sessionId}/complete`),

  startMock: (examId: number) =>
    req<{ mock_id: number; count: number; duration_min: number; questions: Question[] }>(
      "POST", `/exams/${examId}/mocks/start`),
  submitMock: (examId: number, mockId: number) =>
    req<{ score: number; per_element: Record<string, number> }>(
      "POST", `/exams/${examId}/mocks/${mockId}/submit`),

  readiness: (examId: number) => req<Readiness>("GET", `/exams/${examId}/readiness`),
  gamify: () => req<Gamify>("GET", "/me/gamify"),
  listModels: () =>
    req<{ models: { id: string; label: string }[]; selected: string }>("GET", "/models"),
  selectModel: (model_id: string) => req<{ selected: string }>("PUT", "/me/model", { model_id }),
  reportQuestion: (id: number, reason: string) =>
    req<{ reported: boolean }>("POST", `/questions/${id}/report`, { reason }),
  questionsBatch: (ids: number[]) =>
    req<{ questions: Question[] }>("POST", "/questions/batch", { ids }),
  flashcards: (examId: number, rebuild = false) =>
    req<{ deck_id: number; cards: { front: string; back: string; topic_code: string }[];
          cached?: boolean }>(
      "POST", `/exams/${examId}/flashcards${rebuild ? "?rebuild=true" : ""}`),
  buildStarterPack: (examId: number) =>
    req<{ building: boolean; already: boolean }>("POST", `/exams/${examId}/starter-pack`),
};
