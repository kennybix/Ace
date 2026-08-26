// Merges app.json with an optional gitignored app.local.json so deployment-specific
// values (your server addresses) never live in version control.
// app.local.json example: { "extra": { "apiCandidates": ["http://100.x.y.z:8040"] } }
const appJson = require("./app.json");

let local = {};
try {
  local = require("./app.local.json");
} catch {
  // no local overrides — placeholders from app.json apply
}

module.exports = {
  ...appJson.expo,
  extra: { ...appJson.expo.extra, ...(local.extra ?? {}) },
};
