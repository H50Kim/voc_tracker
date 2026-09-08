var FORM_ID = "12jEITV1PpsrhIaDekBKpE5uo5nnQSuZdHye6PPUvxOE";
var ADMIN_EMAIL = "andersona.kim@gmail.com";
var EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
var TOKEN_TTL_SEC = 21600;

function doGet() {
  ensureSetup();
  importFormResponses();
  return HtmlService.createHtmlOutputFromFile("Index")
    .setTitle("VoC Tracker")
    .setXFrameOptionsMode(HtmlService.XFrameOptionsMode.ALLOWALL);
}

function setup() {
  ensureSetup();
  importFormResponses();
}

function bootstrap(token) {
  ensureSetup();
  importFormResponses();
  var googleEmail = getGoogleEmail_();
  if (googleEmail) {
    return login(googleEmail);
  }
  if (token) {
    try {
      return me(token);
    } catch (error) {
      return emptySession_();
    }
  }
  return emptySession_();
}

function login(email) {
  ensureSetup();
  importFormResponses();
  var normalized = normalizeEmail_(email);
  if (!EMAIL_PATTERN.test(normalized)) {
    throw new Error("올바른 이메일 주소를 입력해 주세요.");
  }
  var user = upsertUser_(normalized);
  var token = Utilities.getUuid();
  CacheService.getScriptCache().put("sess:" + token, normalized, TOKEN_TTL_SEC);
  return sessionPayload_(token, normalized, user);
}

function logout(token) {
  if (token) {
    CacheService.getScriptCache().remove("sess:" + token);
  }
  return { ok: true };
}

function me(token) {
  var email = requireEmail_(token);
  var user = upsertUser_(email);
  return sessionPayload_(token, email, user);
}

function listOpinions(token) {
  ensureSetup();
  importFormResponses();
  var session = token ? findSession_(token) : null;
  var email = session || getGoogleEmail_();
  var myHash = email ? hashEmail_(email) : "";
  var admin = email ? isAdmin_(email) : false;
  var opinions = readObjects_("Opinions");
  var votes = readObjects_("Votes");
  var users = readObjects_("Users");
  var userMap = {};
  users.forEach(function (row) {
    userMap[row.emailHash] = row.anonId;
  });
  var voteCount = {};
  var votedSet = {};
  votes.forEach(function (vote) {
    voteCount[vote.opinionId] = (voteCount[vote.opinionId] || 0) + 1;
    if (myHash && vote.emailHash === myHash) {
      votedSet[vote.opinionId] = true;
    }
  });
  assignMissingNumbers_();
  opinions = readObjects_("Opinions");
  var comments = readObjects_("Comments");
  var ratings = readObjects_("Ratings");
  var items = opinions.map(function (row) {
    var mine = myHash !== "" && row.emailHash === myHash;
    var rating = summarizeRatings_(ratings, row.id, myHash);
    return {
      id: row.id,
      number: Number(row.number) || 0,
      numberLabel: formatNumber_(row.number),
      postId: makePostId_(row.id),
      anonId: userMap[row.emailHash] || "VOC-UNKNOWN",
      ask: row.ask,
      others: row.others,
      priority: Number(row.priority),
      votes: voteCount[row.id] || 0,
      voted: Boolean(votedSet[row.id]),
      ratingAvg: rating.avg,
      ratingCount: rating.count,
      myRating: rating.mine,
      mine: mine,
      canManage: admin || mine,
      source: row.source === "google" ? "google" : "app",
      createdAt: toIso_(row.createdAt),
      createdAtLabel: formatDateTime_(row.createdAt),
      updatedAt: toIso_(row.updatedAt),
      updatedAtLabel: formatDateTime_(row.updatedAt),
      comments: comments.filter(function (comment) {
        return comment.opinionId === row.id;
      }).map(function (comment) {
        var commentMine = myHash !== "" && comment.emailHash === myHash;
        return {
          id: comment.id,
          anonId: userMap[comment.emailHash] || "VOC-UNKNOWN",
          body: comment.body,
          createdAt: toIso_(comment.createdAt),
          createdAtLabel: formatDateTime_(comment.createdAt),
          mine: commentMine,
          canManage: admin || commentMine,
        };
      }),
    };
  });
  items.sort(function (a, b) {
    if (b.ratingAvg !== a.ratingAvg) return b.ratingAvg - a.ratingAvg;
    if ((b.number || 0) !== (a.number || 0)) return (a.number || 0) - (b.number || 0);
    return String(b.createdAt).localeCompare(String(a.createdAt));
  });
  return { items: items };
}

function createOpinion(token, ask, others, priority) {
  var email = requireEmail_(token);
  var user = upsertUser_(email);
  var payload = validateOpinion_(ask, others, priority);
  var lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    var now = new Date().toISOString();
    var id = Utilities.getUuid();
    var number = nextNumber_();
    appendObject_("Opinions", {
      id: id,
      number: number,
      emailHash: user.emailHash,
      ask: payload.ask,
      others: payload.others,
      priority: String(payload.priority),
      source: "app",
      createdAt: now,
      updatedAt: now,
    });
    var googleForm = submitToGoogleForm_(email, payload);
    return { ok: true, id: id, number: number, numberLabel: formatNumber_(number), postId: makePostId_(id), googleForm: googleForm };
  } finally {
    lock.releaseLock();
  }
}

function updateOpinion(token, id, ask, others, priority) {
  var email = requireEmail_(token);
  var user = upsertUser_(email);
  var payload = validateOpinion_(ask, others, priority);
  var lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    var rows = readObjects_("Opinions");
    var index = -1;
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].id === id) {
        index = i;
        break;
      }
    }
    if (index < 0) throw new Error("의견을 찾을 수 없습니다.");
    if (!canManageOpinion_(email, user, rows[index])) {
      throw new Error("이 의견을 수정할 권한이 없습니다.");
    }
    rows[index].ask = payload.ask;
    rows[index].others = payload.others;
    rows[index].priority = String(payload.priority);
    rows[index].updatedAt = new Date().toISOString();
    writeObjects_("Opinions", rows);
    var googleForm = submitToGoogleForm_(email, payload);
    return { ok: true, id: rows[index].id, postId: makePostId_(rows[index].id), googleForm: googleForm };
  } finally {
    lock.releaseLock();
  }
}

function deleteOpinion(token, id) {
  var email = requireEmail_(token);
  var user = upsertUser_(email);
  var lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    var rows = readObjects_("Opinions");
    var index = -1;
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].id === id) {
        index = i;
        break;
      }
    }
    if (index < 0) throw new Error("의견을 찾을 수 없습니다.");
    if (!canManageOpinion_(email, user, rows[index])) {
      throw new Error("이 의견을 삭제할 권한이 없습니다.");
    }
    rows.splice(index, 1);
    writeObjects_("Opinions", rows);
    writeObjects_("Votes", readObjects_("Votes").filter(function (row) {
      return row.opinionId !== id;
    }));
    writeObjects_("Comments", readObjects_("Comments").filter(function (row) {
      return row.opinionId !== id;
    }));
    writeObjects_("Ratings", readObjects_("Ratings").filter(function (row) {
      return row.opinionId !== id;
    }));
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

function addComment(token, opinionId, body) {
  var email = requireEmail_(token);
  var user = upsertUser_(email);
  var text = sanitizeText_(body, 1000);
  if (!text) throw new Error("댓글 내용을 입력해 주세요.");
  var opinion = findOpinionById_(opinionId);
  if (!opinion) throw new Error("의견을 찾을 수 없습니다.");
  var lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    var id = Utilities.getUuid();
    appendObject_("Comments", {
      id: id,
      opinionId: opinionId,
      emailHash: user.emailHash,
      body: text,
      createdAt: new Date().toISOString(),
    });
    return { ok: true, id: id };
  } finally {
    lock.releaseLock();
  }
}

function deleteComment(token, commentId) {
  var email = requireEmail_(token);
  var user = upsertUser_(email);
  var lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    var rows = readObjects_("Comments");
    var index = -1;
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].id === commentId) {
        index = i;
        break;
      }
    }
    if (index < 0) throw new Error("댓글을 찾을 수 없습니다.");
    if (!isAdmin_(email) && rows[index].emailHash !== user.emailHash) {
      throw new Error("이 댓글을 삭제할 권한이 없습니다.");
    }
    rows.splice(index, 1);
    writeObjects_("Comments", rows);
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

function rateOpinion(token, opinionId, stars) {
  var email = requireEmail_(token);
  var user = upsertUser_(email);
  var rating = Number(stars);
  if (!isFinite(rating)) throw new Error("별점은 1부터 5 사이여야 합니다.");
  rating = Math.round(rating);
  if (rating < 1 || rating > 5) throw new Error("별점은 1부터 5 사이여야 합니다.");
  var lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    var opinion = findOpinionById_(opinionId);
    if (!opinion) throw new Error("의견을 찾을 수 없습니다.");
    if (opinion.emailHash === user.emailHash) {
      throw new Error("본인 의견에는 별점을 줄 수 없습니다.");
    }
    var rows = readObjects_("Ratings");
    var now = new Date().toISOString();
    var updated = false;
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].emailHash === user.emailHash && rows[i].opinionId === opinionId) {
        rows[i].stars = rating;
        rows[i].updatedAt = now;
        updated = true;
        break;
      }
    }
    if (updated) {
      writeObjects_("Ratings", rows);
    } else {
      appendObject_("Ratings", {
        emailHash: user.emailHash,
        opinionId: opinionId,
        stars: rating,
        createdAt: now,
        updatedAt: now,
      });
    }
    return { ok: true, stars: rating };
  } finally {
    lock.releaseLock();
  }
}

function vote(token, opinionId) {
  var email = requireEmail_(token);
  var user = upsertUser_(email);
  var lock = LockService.getScriptLock();
  lock.waitLock(15000);
  try {
    var opinion = findOpinionById_(opinionId);
    if (!opinion) throw new Error("의견을 찾을 수 없습니다.");
    if (opinion.emailHash === user.emailHash) {
      throw new Error("본인 의견에는 투표할 수 없습니다.");
    }
    var votes = readObjects_("Votes");
    var already = votes.some(function (row) {
      return row.emailHash === user.emailHash && row.opinionId === opinionId;
    });
    if (already) {
      throw new Error("이미 이 의견에 투표했습니다. 투표는 한 번만 가능합니다.");
    }
    appendObject_("Votes", {
      emailHash: user.emailHash,
      opinionId: opinionId,
      createdAt: new Date().toISOString(),
    });
    return { ok: true };
  } finally {
    lock.releaseLock();
  }
}

function importFormResponses() {
  ensureSetup();
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(8000)) return;
  try {
    var form = FormApp.openById(FORM_ID);
    var responses = form.getResponses();
    responses.forEach(function (response) {
      var email = normalizeEmail_(response.getRespondentEmail());
      if (!EMAIL_PATTERN.test(email)) return;
      var answers = readFormAnswers_(response);
      if (!answers.ask) return;
      var priority = parsePriority_(answers.priority);
      if (priority === null) return;
      var user = upsertUser_(email);
      upsertFormOpinion_(user, answers.ask, answers.others, priority, response.getTimestamp());
    });
  } catch (error) {
    console.error("importFormResponses: " + error);
  } finally {
    lock.releaseLock();
  }
}

function ensureSetup() {
  var props = PropertiesService.getScriptProperties();
  if (!props.getProperty("ANON_SECRET")) {
    props.setProperty("ANON_SECRET", Utilities.getUuid().replace(/-/g, "") + Utilities.getUuid().replace(/-/g, ""));
  }
  var spreadsheetId = props.getProperty("SPREADSHEET_ID");
  var ss;
  if (spreadsheetId) {
    try {
      ss = SpreadsheetApp.openById(spreadsheetId);
    } catch (error) {
      ss = null;
    }
  }
  if (!ss) {
    ss = SpreadsheetApp.create("VoC Tracker Data");
    props.setProperty("SPREADSHEET_ID", ss.getId());
  }
  ensureSheet_(ss, "Users", ["emailHash", "anonId", "createdAt"]);
  ensureSheet_(ss, "Opinions", ["id", "emailHash", "ask", "others", "priority", "source", "createdAt", "updatedAt", "number"]);
  ensureSheet_(ss, "Votes", ["emailHash", "opinionId", "createdAt"]);
  ensureSheet_(ss, "Comments", ["id", "opinionId", "emailHash", "body", "createdAt"]);
  ensureSheet_(ss, "Ratings", ["emailHash", "opinionId", "stars", "createdAt", "updatedAt"]);
  assignMissingNumbers_();
}

function ensureSheet_(ss, name, headers) {
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  var first = sheet.getRange(1, 1, 1, headers.length).getValues()[0];
  var missing = headers.some(function (header, index) {
    return String(first[index] || "") !== header;
  });
  if (missing) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  }
}

function getSpreadsheet_() {
  return SpreadsheetApp.openById(
    PropertiesService.getScriptProperties().getProperty("SPREADSHEET_ID"),
  );
}

function getSecret_() {
  return PropertiesService.getScriptProperties().getProperty("ANON_SECRET");
}

function normalizeEmail_(email) {
  return String(email || "").trim().toLowerCase();
}

function isAdmin_(email) {
  return normalizeEmail_(email) === ADMIN_EMAIL;
}

function emptySession_() {
  return { anonId: "", role: "", isAdmin: false, token: "", googleEmail: "" };
}

function sessionPayload_(token, email, user) {
  var admin = isAdmin_(email);
  return {
    token: token,
    anonId: user.anonId,
    role: admin ? "admin" : "user",
    isAdmin: admin,
    googleEmail: getGoogleEmail_(),
  };
}

function makePostId_(id) {
  return "POST-" + String(id || "").replace(/-/g, "").slice(0, 8).toUpperCase();
}

function formatNumber_(value) {
  var number = Number(value);
  if (!isFinite(number) || number < 1) return "";
  var label = String(Math.round(number));
  while (label.length < 3) label = "0" + label;
  return "#" + label;
}

function toIso_(value) {
  if (!value) return "";
  var date = value instanceof Date ? value : new Date(value);
  if (isNaN(date.getTime())) return String(value);
  return date.toISOString();
}

function formatDateTime_(value) {
  if (!value) return "";
  var date = value instanceof Date ? value : new Date(value);
  if (isNaN(date.getTime())) return String(value);
  return Utilities.formatDate(date, "Asia/Seoul", "yyyy-MM-dd HH:mm");
}

function nextNumber_() {
  assignMissingNumbers_();
  var props = PropertiesService.getScriptProperties();
  var next = Number(props.getProperty("NEXT_NUMBER") || "1");
  if (!isFinite(next) || next < 1) next = 1;
  props.setProperty("NEXT_NUMBER", String(next + 1));
  return next;
}

function assignMissingNumbers_() {
  var rows = readObjects_("Opinions");
  var max = 0;
  rows.forEach(function (row) {
    var number = Number(row.number);
    if (isFinite(number) && number > max) max = number;
  });
  var next = max + 1;
  var stored = Number(PropertiesService.getScriptProperties().getProperty("NEXT_NUMBER") || "1");
  if (isFinite(stored) && stored > next) next = stored;
  var changed = false;
  rows.sort(function (a, b) {
    return String(toIso_(a.createdAt)).localeCompare(String(toIso_(b.createdAt)));
  });
  rows.forEach(function (row) {
    var number = Number(row.number);
    if (!isFinite(number) || number < 1) {
      row.number = next;
      next += 1;
      changed = true;
    }
  });
  if (changed) writeObjects_("Opinions", rows);
  PropertiesService.getScriptProperties().setProperty("NEXT_NUMBER", String(next));
}

function summarizeRatings_(ratings, opinionId, myHash) {
  var total = 0;
  var count = 0;
  var mine = 0;
  ratings.forEach(function (row) {
    if (row.opinionId !== opinionId) return;
    var stars = Number(row.stars);
    if (!isFinite(stars)) return;
    total += stars;
    count += 1;
    if (myHash && row.emailHash === myHash) mine = stars;
  });
  return {
    avg: count ? Math.round((total / count) * 10) / 10 : 0,
    count: count,
    mine: mine,
  };
}

function canManageOpinion_(email, user, opinion) {
  if (isAdmin_(email)) return true;
  return Boolean(opinion && user && opinion.emailHash === user.emailHash);
}

function hmacHex_(value, key) {
  return Utilities.computeHmacSha256Signature(String(value), String(key))
    .map(function (byte) {
      return ("0" + ((byte + 256) % 256).toString(16)).slice(-2);
    })
    .join("");
}

function hashEmail_(email) {
  return hmacHex_(email, getSecret_());
}

function makeAnonId_(emailHash) {
  return "VOC-" + hmacHex_(emailHash, getSecret_() + ":anon").slice(0, 8).toUpperCase();
}

function getGoogleEmail_() {
  try {
    var email = normalizeEmail_(Session.getActiveUser().getEmail());
    return EMAIL_PATTERN.test(email) ? email : "";
  } catch (error) {
    return "";
  }
}

function findSession_(token) {
  if (!token) return "";
  return CacheService.getScriptCache().get("sess:" + token) || "";
}

function requireEmail_(token) {
  var email = findSession_(token);
  if (email) return email;
  var googleEmail = getGoogleEmail_();
  if (googleEmail) return googleEmail;
  throw new Error("이메일로 먼저 로그인해 주세요.");
}

function upsertUser_(email) {
  var emailHash = hashEmail_(email);
  var users = readObjects_("Users");
  for (var i = 0; i < users.length; i++) {
    if (users[i].emailHash === emailHash) return users[i];
  }
  var user = {
    emailHash: emailHash,
    anonId: makeAnonId_(emailHash),
    createdAt: new Date().toISOString(),
  };
  appendObject_("Users", user);
  return user;
}

function findOpinionByHash_(emailHash) {
  return readObjects_("Opinions").filter(function (row) {
    return row.emailHash === emailHash;
  })[0] || null;
}

function findOpinionById_(id) {
  return readObjects_("Opinions").filter(function (row) {
    return row.id === id;
  })[0] || null;
}

function upsertFormOpinion_(user, ask, others, priority, timestamp) {
  var rows = readObjects_("Opinions");
  var createdAt = timestamp ? new Date(timestamp).toISOString() : new Date().toISOString();
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].emailHash === user.emailHash && rows[i].source === "google") {
      rows[i].ask = ask;
      rows[i].others = others;
      rows[i].priority = String(priority);
      rows[i].source = "google";
      rows[i].updatedAt = new Date().toISOString();
      writeObjects_("Opinions", rows);
      return;
    }
  }
  appendObject_("Opinions", {
    id: Utilities.getUuid(),
    number: nextNumber_(),
    emailHash: user.emailHash,
    ask: ask,
    others: others,
    priority: String(priority),
    source: "google",
    createdAt: createdAt,
    updatedAt: createdAt,
  });
}

function validateOpinion_(ask, others, priority) {
  var cleanAsk = sanitizeText_(ask, 4000);
  var cleanOthers = sanitizeText_(others, 4000);
  var parsed = parsePriority_(priority);
  if (!cleanAsk) throw new Error("Ask S&E Anything 내용을 입력해 주세요.");
  if (parsed === null) throw new Error("Priority는 0부터 5 사이여야 합니다.");
  return { ask: cleanAsk, others: cleanOthers, priority: parsed };
}

function sanitizeText_(value, maxLength) {
  return String(value || "").replace(/\r\n/g, "\n").trim().slice(0, maxLength);
}

function parsePriority_(value) {
  var priority = Number(value);
  if (!isFinite(priority)) return null;
  priority = Math.round(priority);
  if (priority < 0 || priority > 5) return null;
  return priority;
}

function readFormAnswers_(response) {
  var ask = "";
  var others = "";
  var priority = "";
  response.getItemResponses().forEach(function (itemResponse) {
    var title = String(itemResponse.getItem().getTitle() || "");
    var value = itemResponse.getResponse();
    if (title === "Ask S&E Anything") ask = String(value || "");
    if (title === "Others") others = String(value || "");
    if (title === "Priority") priority = value;
  });
  return { ask: sanitizeText_(ask, 4000), others: sanitizeText_(others, 4000), priority: priority };
}

function submitToGoogleForm_(email, payload) {
  try {
    var form = FormApp.openById(FORM_ID);
    var draft = form.createResponse();
    form.getItems().forEach(function (item) {
      var title = item.getTitle();
      var type = item.getType();
      if (title === "Ask S&E Anything" && type === FormApp.ItemType.PARAGRAPH_TEXT) {
        draft.withItemResponse(item.asParagraphTextItem().createResponse(payload.ask));
      }
      if (title === "Others" && type === FormApp.ItemType.PARAGRAPH_TEXT && payload.others) {
        draft.withItemResponse(item.asParagraphTextItem().createResponse(payload.others));
      }
      if (title === "Priority" && type === FormApp.ItemType.SCALE) {
        draft.withItemResponse(item.asScaleItem().createResponse(payload.priority));
      }
    });
    draft.submit();
    return { ok: true };
  } catch (error) {
    return { ok: false, error: String(error) };
  }
}

function readObjects_(name) {
  var sheet = getSpreadsheet_().getSheetByName(name);
  var values = sheet.getDataRange().getValues();
  if (values.length < 2) return [];
  var headers = values[0];
  return values.slice(1).filter(function (row) {
    return String(row[0] || "") !== "";
  }).map(function (row) {
    var object = {};
    headers.forEach(function (header, index) {
      object[header] = row[index];
    });
    return object;
  });
}

function writeObjects_(name, rows) {
  var sheet = getSpreadsheet_().getSheetByName(name);
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  sheet.getRange(2, 1, Math.max(sheet.getMaxRows() - 1, 1), headers.length).clearContent();
  if (!rows.length) return;
  var values = rows.map(function (row) {
    return headers.map(function (header) {
      return row[header] == null ? "" : row[header];
    });
  });
  sheet.getRange(2, 1, values.length, headers.length).setValues(values);
}

function appendObject_(name, object) {
  var sheet = getSpreadsheet_().getSheetByName(name);
  var headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  sheet.appendRow(headers.map(function (header) {
    return object[header] == null ? "" : object[header];
  }));
}
