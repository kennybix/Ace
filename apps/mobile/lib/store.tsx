import * as SecureStore from "expo-secure-store";
import React, { createContext, useContext, useEffect, useState } from "react";
import { setOnUnauthorized, setToken } from "./api";

const K_TOKEN = "ace.token";
const K_EMAIL = "ace.email";
const K_EXAM = "ace.examId";

type AppState = {
  token: string | null;
  examId: number | null;
  email: string | null;
  restoring: boolean;
  signIn: (token: string, email: string) => void;
  signOut: () => void;
  setExamId: (id: number | null) => void;
};

const Ctx = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [token, setTok] = useState<string | null>(null);
  const [examId, setExamIdState] = useState<number | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [restoring, setRestoring] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [t, e, x] = await Promise.all([
          SecureStore.getItemAsync(K_TOKEN),
          SecureStore.getItemAsync(K_EMAIL),
          SecureStore.getItemAsync(K_EXAM),
        ]);
        if (t) {
          setToken(t);
          setTok(t);
          setEmail(e);
        }
        if (x) setExamIdState(Number(x));
      } finally {
        setRestoring(false);
      }
    })();
  }, []);

  const signIn = (t: string, e: string) => {
    setToken(t);
    setTok(t);
    setEmail(e);
    SecureStore.setItemAsync(K_TOKEN, t);
    SecureStore.setItemAsync(K_EMAIL, e);
  };

  const signOut = () => {
    setToken(null);
    setTok(null);
    setEmail(null);
    setExamIdState(null);
    SecureStore.deleteItemAsync(K_TOKEN);
    SecureStore.deleteItemAsync(K_EMAIL);
    SecureStore.deleteItemAsync(K_EXAM);
  };

  // expired/invalid token anywhere → clean sign-out; the tabs guard routes to login
  useEffect(() => { setOnUnauthorized(() => signOut()); }, []);

  const setExamId = (id: number | null) => {
    setExamIdState(id);
    if (id === null) SecureStore.deleteItemAsync(K_EXAM);
    else SecureStore.setItemAsync(K_EXAM, String(id));
  };

  return (
    <Ctx.Provider value={{ token, examId, email, restoring, signIn, signOut, setExamId }}>
      {children}
    </Ctx.Provider>
  );
}

export function useApp(): AppState {
  const v = useContext(Ctx);
  if (!v) throw new Error("AppProvider missing");
  return v;
}
