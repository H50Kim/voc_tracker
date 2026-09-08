const FORM_RESPONSE_URLS = [
  "https://docs.google.com/forms/d/e/1FAIpQLSdn3H9cm8OGe8UC5geN3Ogy_MGxi7BGUSKwsHOIAuGxeJwXaQ/formResponse",
  "https://docs.google.com/forms/d/12jEITV1PpsrhIaDekBKpE5uo5nnQSuZdHye6PPUvxOE/formResponse",
];

const ENTRIES = {
  ask: "entry.1173889863",
  others: "entry.619676855",
  priority: "entry.499148274",
};

export const GOOGLE_FORM_EDIT_URL =
  "https://docs.google.com/forms/d/12jEITV1PpsrhIaDekBKpE5uo5nnQSuZdHye6PPUvxOE/edit";

export const QUESTION_IDS = {
  ask: "1173889863",
  others: "619676855",
  priority: "499148274",
};

function buildBody({ email, ask, others, priority }) {
  const body = new URLSearchParams();
  body.set(ENTRIES.ask, ask);
  body.set(ENTRIES.others, others);
  body.set(ENTRIES.priority, String(priority));
  if (email) body.set("emailAddress", email);
  body.set("fvv", "1");
  body.set("partialResponse", "[null,null,\"-1\"]");
  body.set("pageHistory", "0");
  return body;
}

function looksRecorded(status, text) {
  if (status >= 200 && status < 400) {
    if (!text) return true;
    if (/응답이 기록|Your response has been recorded|제출되었습니다/i.test(text)) {
      return true;
    }
    if (/응답을 받지|not accepting responses|페이지를 찾을 수 없음/i.test(text)) {
      return false;
    }
    return status === 200 || status === 302;
  }
  return false;
}

export async function submitToGoogleForm({ email, ask, others, priority }) {
  const body = buildBody({ email, ask, others, priority });
  let lastError = "Google Form에 저장하지 못했습니다.";

  for (const url of FORM_RESPONSE_URLS) {
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent":
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
      },
      body,
      redirect: "follow",
    });
    const text = await response.text();
    if (looksRecorded(response.status, text)) {
      return { ok: true, status: response.status };
    }
    lastError =
      response.status === 401
        ? "Google Form이 게시되지 않았거나 응답을 받지 않습니다. 폼에서 게시를 켜 주세요."
        : `Google Form 저장 실패 (${response.status})`;
  }

  throw new Error(lastError);
}
