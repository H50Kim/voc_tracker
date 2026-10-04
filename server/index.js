import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";
import { mkdir, readFile, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import express from "express";
import { GOOGLE_FORM_EDIT_URL, submitToGoogleForm } from "./googleForm.js";
import { createStore } from "./store.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const rootDir = path.resolve(__dirname, "..");
const dataDir = path.join(rootDir, "data");
const secretFile = path.join(dataDir, ".secret");
const dbFile = path.join(dataDir, "db.json");

const PORT = Number(process.env.PORT) || 4173;
const ADMIN_EMAIL = String(process.env.ADMIN_EMAIL ?? "andersona.kim@gmail.com")
  .trim()
  .toLowerCase();
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const COOKIE_SECURE =
  process.env.COOKIE_SECURE === "true" || process.env.NODE_ENV === "production";

const store = createStore(dbFile);
let secret = "";
let adminEmailHash = "";
const googleResponsesFile = path.join(dataDir, "google-responses.json");
let googleResponsesMtimeMs = -1;
let googleImportBusy = false;

async function loadSecret() {
  await mkdir(dataDir, { recursive: true });
  try {
    secret = (await readFile(secretFile, "utf8")).trim();
    if (secret.length >= 32) return;
  } catch (error) {
    if (!error || error.code !== "ENOENT") throw error;
  }
  secret = randomBytes(32).toString("hex");
  await writeFile(secretFile, secret, "utf8");
}

function normalizeEmail(email) {
  return String(email ?? "")
    .trim()
    .toLowerCase();
}

function hashEmail(email) {
  return createHmac("sha256", secret).update(email).digest("hex");
}

function isAdminHash(emailHash) {
  return Boolean(emailHash && adminEmailHash && emailHash === adminEmailHash);
}

function makePostId(id) {
  return `POST-${String(id || "").replace(/-/g, "").slice(0, 8).toUpperCase()}`;
}

function formatNumber(value) {
  const number = Number(value);
  if (!Number.isFinite(number) || number < 1) return "";
  return `#${String(Math.round(number)).padStart(3, "0")}`;
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).formatToParts(date);
  const pick = (type) => parts.find((part) => part.type === type)?.value ?? "";
  return `${pick("year")}-${pick("month")}-${pick("day")} ${pick("hour")}:${pick("minute")}`;
}

function canManage(emailHash, userId, opinion) {
  if (isAdminHash(emailHash)) return true;
  return Boolean(opinion && userId && opinion.userId === userId);
}

function makeAnonId(emailHash) {
  const digest = createHmac("sha256", `${secret}:anon`)
    .update(emailHash)
    .digest("hex")
    .slice(0, 8)
    .toUpperCase();
  return `VOC-${digest}`;
}

function signToken(userId, emailHash) {
  const payload = Buffer.from(JSON.stringify({ userId, emailHash }), "utf8").toString(
    "base64url",
  );
  const signature = createHmac("sha256", `${secret}:token`)
    .update(payload)
    .digest("base64url");
  return `${payload}.${signature}`;
}

function verifyToken(token) {
  if (!token || !token.includes(".")) return null;
  const dot = token.indexOf(".");
  const payload = token.slice(0, dot);
  const signature = token.slice(dot + 1);
  const expected = createHmac("sha256", `${secret}:token`)
    .update(payload)
    .digest("base64url");
  const left = Buffer.from(signature);
  const right = Buffer.from(expected);
  if (left.length !== right.length || !timingSafeEqual(left, right)) {
    return null;
  }
  try {
    const data = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    if (typeof data.userId !== "string") return null;
    if (typeof data.emailHash === "string" && data.emailHash) {
      return { userId: data.userId, emailHash: data.emailHash };
    }
    if (typeof data.email === "string" && data.email) {
      return {
        userId: data.userId,
        emailHash: hashEmail(normalizeEmail(data.email)),
      };
    }
    return null;
  } catch {
    return null;
  }
}

function readToken(req) {
  const header = req.get("authorization") ?? "";
  if (header.startsWith("Bearer ")) return header.slice(7).trim();
  const cookie = req.get("cookie") ?? "";
  const match = cookie.match(/(?:^|;\s*)voc_session=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function requireUser(req, res, next) {
  const session = verifyToken(readToken(req));
  const user = session?.userId ? store.findUserById(session.userId) : null;
  if (!user) {
    res.status(401).json({ error: "이메일로 먼저 입장해 주세요." });
    return;
  }
  req.user = user;
  req.emailHash = session.emailHash;
  req.syncEmail = user.loginEmail || "";
  next();
}

function sanitizeText(value, maxLength) {
  return String(value ?? "")
    .replace(/\r\n/g, "\n")
    .trim()
    .slice(0, maxLength);
}

function parsePriority(value) {
  const priority = Number(value);
  if (!Number.isInteger(priority) || priority < 0 || priority > 5) return null;
  return priority;
}

function summarizeRatings(opinionId, currentUserId) {
  const ratings = store.listRatings(opinionId);
  const total = ratings.reduce((sum, rating) => sum + Number(rating.stars || 0), 0);
  const mine = currentUserId
    ? ratings.find((rating) => rating.userId === currentUserId)?.stars ?? 0
    : 0;
  return {
    avg: ratings.length ? Math.round((total / ratings.length) * 10) / 10 : 0,
    count: ratings.length,
    mine,
  };
}

function publicComment(comment, currentUserId, emailHash = "") {
  const author = store.findUserById(comment.userId);
  const mine = currentUserId === comment.userId;
  return {
    id: comment.id,
    anonId: author?.anonId ?? "VOC-UNKNOWN",
    body: comment.body,
    createdAt: comment.createdAt,
    createdAtLabel: formatDateTime(comment.createdAt),
    mine,
    canManage: isAdminHash(emailHash) || mine,
  };
}

function titleOfOpinion(opinion) {
  return String(opinion?.ask || "")
    .split("\n")[0]
    .trim();
}

function publicOpinion(opinion, currentUserId, emailHash = "", options = {}) {
  const includeComments = options.includeComments !== false;
  const author = store.findUserById(opinion.userId);
  const mine = currentUserId === opinion.userId;
  const rating = summarizeRatings(opinion.id, currentUserId);
  return {
    id: opinion.id,
    number: Number(opinion.number) || 0,
    numberLabel: formatNumber(opinion.number),
    postId: makePostId(opinion.id),
    anonId: author?.anonId ?? "VOC-UNKNOWN",
    ask: opinion.ask,
    others: opinion.others,
    priority: opinion.priority,
    votes: store.countVotes(opinion.id),
    voted: currentUserId ? Boolean(store.findVote(currentUserId, opinion.id)) : false,
    ratingAvg: rating.avg,
    ratingCount: rating.count,
    myRating: rating.mine,
    mine,
    canManage: canManage(emailHash, currentUserId, opinion),
    source: opinion.source === "google" ? "google" : "app",
    createdAt: opinion.createdAt,
    createdAtLabel: formatDateTime(opinion.createdAt),
    updatedAt: opinion.updatedAt,
    updatedAtLabel: formatDateTime(opinion.updatedAt),
    commentCount: store.countComments(opinion.id),
    comments: includeComments
      ? store.listComments(opinion.id).map((comment) =>
          publicComment(comment, currentUserId, emailHash),
        )
      : [],
  };
}

async function importGoogleRespondentsIfStale() {
  let mtimeMs = 0;
  try {
    mtimeMs = (await stat(googleResponsesFile)).mtimeMs;
  } catch (error) {
    if (!error || error.code !== "ENOENT") throw error;
    googleResponsesMtimeMs = 0;
    return;
  }
  if (mtimeMs === googleResponsesMtimeMs || googleImportBusy) return;
  googleImportBusy = true;
  try {
    await importGoogleRespondents();
    googleResponsesMtimeMs = mtimeMs;
  } finally {
    googleImportBusy = false;
  }
}

async function importGoogleRespondents() {
  let payload = { responses: [] };
  try {
    payload = JSON.parse(await readFile(googleResponsesFile, "utf8"));
  } catch (error) {
    if (!error || error.code !== "ENOENT") throw error;
  }

  const responses = Array.isArray(payload.responses) ? payload.responses : [];
  for (const item of responses) {
    const email = normalizeEmail(item.email);
    if (!EMAIL_PATTERN.test(email)) continue;
    const emailHash = hashEmail(email);
    const user = await store.createUser({
      emailHash,
      anonId: makeAnonId(emailHash),
    });
    const ask = sanitizeText(item.ask, 4000);
    if (!ask) continue;
    const others = sanitizeText(item.others, 4000);
    const priority = parsePriority(item.priority);
    if (priority === null) continue;
    await store.upsertFormOpinion({
      userId: user.id,
      ask,
      others,
      priority,
      formKey: `google:${emailHash}`,
      createdAt: item.submittedAt || new Date().toISOString(),
    });
  }
}

async function syncGoogleForm(payload) {
  try {
    await submitToGoogleForm(payload);
    return { ok: true, formUrl: GOOGLE_FORM_EDIT_URL };
  } catch (error) {
    return {
      ok: false,
      error: error.message,
      formUrl: GOOGLE_FORM_EDIT_URL,
    };
  }
}

function cookieSuffix() {
  return COOKIE_SECURE ? "; Secure" : "";
}

function setSessionCookie(res, token) {
  res.setHeader(
    "Set-Cookie",
    `voc_session=${encodeURIComponent(token)}; HttpOnly; SameSite=Lax; Path=/${cookieSuffix()}`,
  );
}

function clearSessionCookie(res) {
  res.setHeader(
    "Set-Cookie",
    `voc_session=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0${cookieSuffix()}`,
  );
}

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "32kb" }));
app.use(express.static(path.join(rootDir, "public")));

app.post("/api/auth/logout", (req, res) => {
  clearSessionCookie(res);
  res.json({ ok: true });
});

app.post("/api/auth", async (req, res) => {
  const email = normalizeEmail(req.body?.email);
  if (!EMAIL_PATTERN.test(email)) {
    res.status(400).json({ error: "올바른 이메일 주소를 입력해 주세요." });
    return;
  }

  const emailHash = hashEmail(email);
  let user = store.findUserByEmailHash(emailHash);
  if (!user) {
    user = await store.createUser({
      emailHash,
      anonId: makeAnonId(emailHash),
    });
  }
  await store.touchUserLogin(user.id, email);

  const token = signToken(user.id, emailHash);
  setSessionCookie(res, token);
  res.json({
    anonId: user.anonId,
    token,
    role: isAdminHash(emailHash) ? "admin" : "user",
    isAdmin: isAdminHash(emailHash),
  });
});

app.get("/api/me", requireUser, (req, res) => {
  res.json({
    anonId: req.user.anonId,
    role: isAdminHash(req.emailHash) ? "admin" : "user",
    isAdmin: isAdminHash(req.emailHash),
  });
});

app.get("/api/me/comments", requireUser, (req, res) => {
  const items = store.listCommentsByUser(req.user.id).map((comment) => {
    const opinion = store.findOpinionById(comment.opinionId);
    return {
      ...publicComment(comment, req.user.id, req.emailHash),
      opinionId: comment.opinionId,
      numberLabel: formatNumber(opinion?.number),
      title: titleOfOpinion(opinion) || "제목 없음",
    };
  });
  res.json({ items });
});

app.get("/api/opinions/:id", async (req, res) => {
  await importGoogleRespondentsIfStale();
  const opinion = store.findOpinionById(req.params.id);
  if (!opinion) {
    res.status(404).json({ error: "의견을 찾을 수 없습니다." });
    return;
  }
  const session = verifyToken(readToken(req));
  const userId = session?.userId ?? "";
  const emailHash = session?.emailHash ?? "";
  res.json({ item: publicOpinion(opinion, userId, emailHash) });
});

app.get("/api/opinions", async (req, res) => {
  await importGoogleRespondentsIfStale();
  const session = verifyToken(readToken(req));
  const userId = session?.userId ?? "";
  const emailHash = session?.emailHash ?? "";
  const items = store
    .listOpinions()
    .map((item) => publicOpinion(item, userId, emailHash, { includeComments: false }));
  res.json({ items });
});

app.post("/api/opinions", requireUser, async (req, res) => {
  const ask = sanitizeText(req.body?.ask, 4000);
  const others = sanitizeText(req.body?.others, 4000);
  const priority = parsePriority(req.body?.priority);
  if (!ask) {
    res.status(400).json({ error: "Ask S&E Anything 내용을 입력해 주세요." });
    return;
  }
  if (priority === null) {
    res.status(400).json({ error: "Priority는 0부터 5 사이여야 합니다." });
    return;
  }

  const googleForm = await syncGoogleForm({
    email: req.syncEmail,
    ask,
    others,
    priority,
  });

  const opinion = await store.createOpinion({
    userId: req.user.id,
    ask,
    others,
    priority,
  });
  res.status(201).json({
    item: publicOpinion(opinion, req.user.id, req.emailHash),
    googleForm,
  });
});

app.put("/api/opinions/:id", requireUser, async (req, res) => {
  const existing = store.findOpinionById(req.params.id);
  if (!existing) {
    res.status(404).json({ error: "의견을 찾을 수 없습니다." });
    return;
  }
  if (!canManage(req.emailHash, req.user.id, existing)) {
    res.status(403).json({ error: "이 의견을 수정할 권한이 없습니다." });
    return;
  }

  const ask = sanitizeText(req.body?.ask, 4000);
  const others = sanitizeText(req.body?.others, 4000);
  const priority = parsePriority(req.body?.priority);
  if (!ask) {
    res.status(400).json({ error: "Ask S&E Anything 내용을 입력해 주세요." });
    return;
  }
  if (priority === null) {
    res.status(400).json({ error: "Priority는 0부터 5 사이여야 합니다." });
    return;
  }

  const googleForm = await syncGoogleForm({
    email: req.syncEmail,
    ask,
    others,
    priority,
  });

  const opinion = await store.updateOpinion(existing.id, { ask, others, priority });
  res.json({
    item: publicOpinion(opinion, req.user.id, req.emailHash),
    googleForm,
  });
});

app.delete("/api/opinions/:id", requireUser, async (req, res) => {
  const existing = store.findOpinionById(req.params.id);
  if (!existing) {
    res.status(404).json({ error: "의견을 찾을 수 없습니다." });
    return;
  }
  if (!canManage(req.emailHash, req.user.id, existing)) {
    res.status(403).json({ error: "이 의견을 삭제할 권한이 없습니다." });
    return;
  }
  await store.deleteOpinion(existing.id);
  res.json({ ok: true });
});

app.post("/api/opinions/:id/comments", requireUser, async (req, res) => {
  const opinion = store.findOpinionById(req.params.id);
  if (!opinion) {
    res.status(404).json({ error: "의견을 찾을 수 없습니다." });
    return;
  }
  const body = sanitizeText(req.body?.body, 1000);
  if (!body) {
    res.status(400).json({ error: "댓글 내용을 입력해 주세요." });
    return;
  }
  const comment = await store.addComment({
    opinionId: opinion.id,
    userId: req.user.id,
    body,
  });
  res.status(201).json({ item: publicComment(comment, req.user.id, req.emailHash) });
});

app.put("/api/comments/:id", requireUser, async (req, res) => {
  const comment = store.findCommentById(req.params.id);
  if (!comment) {
    res.status(404).json({ error: "댓글을 찾을 수 없습니다." });
    return;
  }
  if (!isAdminHash(req.emailHash) && comment.userId !== req.user.id) {
    res.status(403).json({ error: "이 댓글을 수정할 권한이 없습니다." });
    return;
  }
  const body = sanitizeText(req.body?.body, 1000);
  if (!body) {
    res.status(400).json({ error: "댓글 내용을 입력해 주세요." });
    return;
  }
  const updated = await store.updateComment(comment.id, body);
  res.json({ item: publicComment(updated, req.user.id, req.emailHash) });
});

app.delete("/api/comments/:id", requireUser, async (req, res) => {
  const comment = store.findCommentById(req.params.id);
  if (!comment) {
    res.status(404).json({ error: "댓글을 찾을 수 없습니다." });
    return;
  }
  if (!isAdminHash(req.emailHash) && comment.userId !== req.user.id) {
    res.status(403).json({ error: "이 댓글을 삭제할 권한이 없습니다." });
    return;
  }
  await store.deleteComment(comment.id);
  res.json({ ok: true });
});

app.post("/api/opinions/:id/rate", requireUser, async (req, res) => {
  const opinion = store.findOpinionById(req.params.id);
  if (!opinion) {
    res.status(404).json({ error: "의견을 찾을 수 없습니다." });
    return;
  }
  if (opinion.userId === req.user.id) {
    res.status(403).json({ error: "본인 의견에는 별점을 줄 수 없습니다." });
    return;
  }
  const stars = Number(req.body?.stars);
  if (!Number.isInteger(stars) || stars < 1 || stars > 5) {
    res.status(400).json({ error: "별점은 1부터 5 사이여야 합니다." });
    return;
  }
  await store.upsertRating(req.user.id, opinion.id, stars);
  const rating = summarizeRatings(opinion.id, req.user.id);
  res.json({
    id: opinion.id,
    ratingAvg: rating.avg,
    ratingCount: rating.count,
    myRating: rating.mine,
  });
});

app.post("/api/opinions/:id/vote", requireUser, async (req, res) => {
  const opinion = store.findOpinionById(req.params.id);
  if (!opinion) {
    res.status(404).json({ error: "의견을 찾을 수 없습니다." });
    return;
  }
  if (opinion.userId === req.user.id) {
    res.status(403).json({ error: "본인 의견에는 투표할 수 없습니다." });
    return;
  }
  const vote = await store.addVote(req.user.id, opinion.id);
  if (!vote) {
    res.status(409).json({ error: "이미 이 의견에 투표했습니다. 투표는 한 번만 가능합니다." });
    return;
  }
  const updated = store.findOpinionById(opinion.id);
  res.json({
    id: updated.id,
    votes: store.countVotes(updated.id),
    voted: true,
  });
});

app.use((error, _req, res, _next) => {
  console.error(error);
  res.status(500).json({ error: "서버 오류가 발생했습니다." });
});

await loadSecret();
adminEmailHash = hashEmail(normalizeEmail(ADMIN_EMAIL));
await store.load();
await importGoogleRespondents();
try {
  googleResponsesMtimeMs = (await stat(googleResponsesFile)).mtimeMs;
} catch (error) {
  if (!error || error.code !== "ENOENT") throw error;
  googleResponsesMtimeMs = 0;
}

app.listen(PORT, () => {
  console.log(`VoC Tracker running at http://localhost:${PORT}`);
});
