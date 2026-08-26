ALTER TABLE questions ADD COLUMN last_reviewed_at timestamptz;
ALTER TABLE questions ADD COLUMN critique_notes jsonb NOT NULL DEFAULT '[]';
