const state = {
  token: localStorage.getItem("voc_token") || "",
  anonId: "",
  role: "",
  isAdmin: false,
  editingId: "",
  selectedId: "",
  view: "home",
  sort: "hot",
  topic: "all",
  query: "",
  editingCommentId: "",
  items: [],
};

const els = {
  backBtn: document.querySelector("#back-btn"),
  headerWrite: document.querySelector("#header-write"),
  topicTabs: document.querySelector("#topic-tabs"),
  viewHome: document.querySelector("#view-home"),
  viewDetail: document.querySelector("#view-detail"),
  viewWrite: document.querySelector("#view-write"),
  viewMe: document.querySelector("#view-me"),
  gate: document.querySelector("#gate"),
  meCard: document.querySelector("#me-card"),
  identity: document.querySelector("#me-card"),
  anonLabel: document.querySelector("#anon-label"),
  roleLabel: document.querySelector("#role-label"),
  logout: document.querySelector("#logout"),
  composerTitle: document.querySelector("#composer-title"),
  composerHint: document.querySelector("#composer-hint"),
  submit: document.querySelector("#submit-opinion"),
  authForm: document.querySelector("#auth-form"),
  opinionForm: document.querySelector("#opinion-form"),
  authError: document.querySelector("#auth-error"),
  formError: document.querySelector("#form-error"),
  feed: document.querySelector("#feed"),
  detail: document.querySelector("#detail"),
  boardMeta: document.querySelector("#board-meta"),
  topicBar: document.querySelector("#topic-bar"),
  search: document.querySelector("#search"),
  myPosts: document.querySelector("#my-posts"),
  myComments: document.querySelector("#my-comments"),
  myPostList: document.querySelector("#my-post-list"),
  myCommentList: document.querySelector("#my-comment-list"),
  myPostsBtn: document.querySelector("#my-posts-btn"),
};

function showError(node, message, ok) {
  if (!node) return;
  if (!message) {
    node.hidden = true;
    node.textContent = "";
    node.className = "error";
    return;
  }
  node.hidden = false;
  node.className = ok ? "ok" : "error";
  node.textContent = message;
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "요청에 실패했습니다.");
  return data;
}

function priorityLabel(value) {
  const labels = ["Low", "낮음", "보통", "높음", "매우 높음", "Super"];
  return labels[value] ?? String(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function relativeTime(iso, fallback) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return fallback || "";
  const diff = Date.now() - date.getTime();
  if (diff < 60_000) return "방금";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}분 전`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}시간 전`;
  if (diff < 86_400_000 * 7) return `${Math.floor(diff / 86_400_000)}일 전`;
  return fallback || "";
}

function titleOf(item) {
  return String(item.ask || "").split("\n")[0].trim() || "제목 없음";
}

function previewOf(item) {
  const extra = item.others ? `\n${item.others}` : "";
  return `${item.ask || ""}${extra}`.trim();
}

function findItem(id) {
  return state.items.find((item) => item.id === id) ?? null;
}

function visibleItems() {
  const query = state.query.trim().toLowerCase();
  const items = state.items.filter((item) => {
    if (state.topic === "form" && item.source !== "google") return false;
    if (state.topic === "app" && item.source === "google") return false;
    if (state.topic === "mine" && !item.mine) return false;
    if (/^[0-5]$/.test(state.topic) && Number(item.priority) !== Number(state.topic)) return false;
    if (!query) return true;
    const haystack = [
      item.ask,
      item.others,
      item.anonId,
      item.numberLabel,
      item.postId,
      priorityLabel(item.priority),
      item.source === "google" ? "form google" : "s&e app",
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });
  if (state.sort === "new") {
    items.sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
    return items;
  }
  if (state.sort === "all") {
    items.sort((a, b) => (a.number || 0) - (b.number || 0));
    return items;
  }
  items.sort((a, b) => {
    if ((b.votes || 0) !== (a.votes || 0)) return (b.votes || 0) - (a.votes || 0);
    if (b.ratingAvg !== a.ratingAvg) return b.ratingAvg - a.ratingAvg;
    return (b.comments?.length || 0) - (a.comments?.length || 0);
  });
  return items;
}

function setView(view) {
  state.view = view;
  els.viewHome.classList.toggle("hidden", view !== "home");
  els.viewDetail.classList.toggle("hidden", view !== "detail");
  els.viewWrite.classList.toggle("hidden", view !== "write");
  els.viewMe.classList.toggle("hidden", view !== "me");
  els.topicTabs.classList.toggle("hidden", view !== "home");
  if (els.topicBar) {
    const topicOpen = view === "home" && document.querySelector('.tab[data-mode="topic"]')?.classList.contains("active");
    els.topicBar.classList.toggle("hidden", !topicOpen);
  }
  els.backBtn.classList.toggle("hidden", view === "home");
  document.querySelectorAll(".nav-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view || (view === "detail" && button.dataset.view === "home"));
  });
  window.scrollTo(0, 0);
}

function renderIdentity() {
  const loggedIn = Boolean(state.anonId);
  els.meCard.classList.toggle("hidden", !loggedIn);
  els.gate.classList.toggle("hidden", loggedIn);
  if (els.anonLabel) els.anonLabel.textContent = state.anonId || "";
  if (els.roleLabel) {
    els.roleLabel.textContent = state.isAdmin ? "관리자" : "User";
    els.roleLabel.className = state.isAdmin ? "chip admin" : "chip role";
  }
  renderMyActivity();
}

function myComments() {
  return state.items.flatMap((item) =>
    (item.comments || [])
      .filter((comment) => comment.mine)
      .map((comment) => ({ ...comment, opinionId: item.id, numberLabel: item.numberLabel, title: titleOf(item) })),
  );
}

function renderMyActivity() {
  const posts = state.items.filter((item) => item.mine);
  const comments = myComments();
  if (els.myPosts) els.myPosts.classList.toggle("hidden", !state.anonId);
  if (els.myComments) els.myComments.classList.toggle("hidden", !state.anonId);
  if (els.myPostList) {
    els.myPostList.innerHTML = posts.length
      ? posts
          .map(
            (item) =>
              `<button type="button" class="me-list-item" data-open="${item.id}"><strong>${escapeHtml(item.numberLabel || "")} ${escapeHtml(titleOf(item))}</strong><span>${escapeHtml(relativeTime(item.createdAt, item.createdAtLabel))} · 댓글 ${(item.comments || []).length} · 공감 ${item.votes || 0}</span></button>`,
          )
          .join("")
      : `<p class="hint">작성한 글이 없습니다.</p>`;
  }
  if (els.myCommentList) {
    els.myCommentList.innerHTML = comments.length
      ? comments
          .map(
            (comment) =>
              `<button type="button" class="me-list-item" data-open="${comment.opinionId}"><strong>${escapeHtml(comment.body)}</strong><span>${escapeHtml(comment.numberLabel || "")} · ${escapeHtml(comment.title)}</span></button>`,
          )
          .join("")
      : `<p class="hint">작성한 댓글이 없습니다.</p>`;
  }
}

function fillForm(item) {
  document.querySelector("#ask").value = item?.ask ?? "";
  document.querySelector("#others").value = item?.others ?? "";
  const priority = String(item?.priority ?? 2);
  const radio = document.querySelector(`input[name="priority"][value="${priority}"]`);
  if (radio) radio.checked = true;
}

function renderComposer() {
  const editing = findItem(state.editingId);
  if (editing) {
    els.composerTitle.textContent = `글 수정 · ${editing.numberLabel}`;
    els.composerHint.textContent = `${editing.anonId} · ${editing.createdAtLabel}`;
    els.submit.textContent = "수정 저장";
  } else {
    els.composerTitle.textContent = "글쓰기";
    els.composerHint.textContent = "익명으로 게시됩니다. 이메일은 노출되지 않습니다.";
    els.submit.textContent = "익명으로 게시";
  }
}

function renderRating(item) {
  const disabled = !state.anonId || item.mine ? "disabled" : "";
  const buttons = [1, 2, 3, 4, 5]
    .map((stars) => {
      let filled = stars <= Math.round(item.ratingAvg || 0) ? " filled" : "";
      if (item.myRating && stars <= item.myRating) filled = " filled mine";
      return `<button type="button" class="star-btn${filled}" data-id="${item.id}" data-stars="${stars}" ${disabled} aria-label="${stars}점">★</button>`;
    })
    .join("");
  let summary = item.ratingCount ? `${Number(item.ratingAvg).toFixed(1)} · ${item.ratingCount}명` : "별점 없음";
  if (item.myRating) summary += ` · 내 별점 ${item.myRating}`;
  return `<div class="rating"><div class="stars">${buttons}</div><span class="rating-meta">${summary}</span></div>`;
}

function renderComments(item) {
  const comments = item.comments || [];
  const list = comments.length
    ? comments
        .map((comment) => {
          const manage = comment.canManage
            ? `<button type="button" class="ghost comment-edit-btn" data-comment-id="${comment.id}">수정</button><button type="button" class="comment-del" data-comment-id="${comment.id}">삭제</button>`
            : "";
          const body =
            state.editingCommentId === comment.id
              ? `<form class="comment-edit" data-comment-id="${comment.id}"><input name="body" maxlength="1000" required value="${escapeHtml(comment.body)}" /><button type="submit">저장</button></form>`
              : `<p>${escapeHtml(comment.body)}</p>`;
          return `<li class="comment">
            <div class="comment-meta">
              <span>${escapeHtml(comment.anonId)}</span>
              <time>${escapeHtml(relativeTime(comment.createdAt, comment.createdAtLabel))}</time>
              ${manage}
            </div>
            ${body}
          </li>`;
        })
        .join("")
    : `<li class="hint">첫 댓글을 남겨 보세요.</li>`;
  const form = state.anonId
    ? `<form class="comment-form" data-id="${item.id}">
        <input name="body" maxlength="1000" required placeholder="익명 댓글 남기기" />
        <button type="submit">등록</button>
      </form>`
    : `<p class="hint">로그인하면 댓글, 별점, 공감을 남길 수 있습니다.</p>`;
  return `<div class="comments"><h3 class="subhead">댓글 ${comments.length}</h3><ul>${list}</ul>${form}</div>`;
}

function renderFeed() {
  const items = visibleItems();
  const label = state.query || state.topic !== "all" ? "검색 결과" : "개의 익명 게시글";
  els.boardMeta.textContent = items.length
    ? state.query || state.topic !== "all"
      ? `${items.length}개 ${label}`
      : `${items.length}개의 익명 게시글`
    : "조건에 맞는 게시글이 없습니다.";
  if (!items.length) {
    els.feed.innerHTML = `<div class="empty">${state.items.length ? "다른 토픽이나 검색어를 선택해 보세요." : "첫 익명 글을 남겨 보세요."}</div>`;
    return;
  }
  els.feed.innerHTML = items
    .map((item) => {
      const comments = item.comments?.length || 0;
      return `<button type="button" class="post" data-open="${item.id}">
        <div class="post-top">
          <span class="company">${item.source === "google" ? "Form" : "S&E"}</span>
          <span>${escapeHtml(item.anonId)}</span>
          <span>·</span>
          <span>${escapeHtml(relativeTime(item.createdAt, item.createdAtLabel))}</span>
          <span>·</span>
          <span>${escapeHtml(item.numberLabel || "")}</span>
        </div>
        <h2>${escapeHtml(titleOf(item))}</h2>
        <p class="preview">${escapeHtml(previewOf(item))}</p>
        <div class="eng">
          <span>공감 ${item.votes || 0}</span>
          <span>★ ${item.ratingCount ? Number(item.ratingAvg).toFixed(1) : "-"}</span>
          <span>댓글 ${comments}</span>
          <span>${escapeHtml(priorityLabel(item.priority))}</span>
        </div>
      </button>`;
    })
    .join("");
}

function renderDetail() {
  const item = findItem(state.selectedId);
  if (!item) {
    els.detail.innerHTML = `<div class="empty">글을 찾을 수 없습니다.</div>`;
    return;
  }
  const voteDisabled = !state.anonId || item.mine || item.voted ? "disabled" : "";
  const voteClass = item.voted ? "ghost vote-btn on" : "ghost vote-btn";
  const manage = item.canManage
    ? `<button type="button" class="ghost edit-btn" data-id="${item.id}">수정</button>
        <button type="button" class="danger delete-btn" data-id="${item.id}">삭제</button>`
    : "";
  els.detail.innerHTML = `
    <div class="detail">
    <div class="post-top">
      <span class="company">${item.source === "google" ? "Form" : "S&E"}</span>
      <span>${escapeHtml(item.anonId)}</span>
      <span>·</span>
      <span>${escapeHtml(item.createdAtLabel || "")}</span>
      ${item.updatedAt && item.updatedAt !== item.createdAt ? `<span>· 수정 ${escapeHtml(item.updatedAtLabel || "")}</span>` : ""}
      ${item.mine ? "<span>· 내 글</span>" : ""}
    </div>
    <h1>${escapeHtml(titleOf(item))}</h1>
    <p class="body">${escapeHtml(item.ask || "")}</p>
    ${item.others ? `<p class="body">${escapeHtml(item.others)}</p>` : ""}
    <div class="eng">
      <span>고유번호 ${escapeHtml(item.numberLabel || "")}</span>
      <span>${escapeHtml(item.postId || "")}</span>
      <span>${escapeHtml(priorityLabel(item.priority))}</span>
    </div>
    ${renderRating(item)}
    <div class="actions">
      <button type="button" class="${voteClass}" data-id="${item.id}" ${voteDisabled}>공감 ${item.votes || 0}</button>
      ${manage}
    </div>
    ${renderComments(item)}
    </div>
  `;
}

function renderAll() {
  renderIdentity();
  renderComposer();
  renderFeed();
  if (state.view === "detail") renderDetail();
}

function openDetail(id) {
  state.selectedId = id;
  setView("detail");
  renderDetail();
}

function startCreate() {
  if (!state.anonId) {
    setView("me");
    return;
  }
  state.editingId = "";
  fillForm(null);
  showError(els.formError, "");
  renderComposer();
  setView("write");
}

function startEdit(id) {
  const item = findItem(id);
  if (!item || !item.canManage) return;
  state.editingId = item.id;
  fillForm(item);
  showError(els.formError, "");
  renderComposer();
  setView("write");
}

function clearSession() {
  state.token = "";
  state.anonId = "";
  state.role = "";
  state.isAdmin = false;
  state.editingId = "";
  localStorage.removeItem("voc_token");
}

async function loadOpinions() {
  const data = await api("/api/opinions");
  state.items = data.items || [];
  if (state.editingId && !findItem(state.editingId)) state.editingId = "";
  if (state.selectedId && !findItem(state.selectedId) && state.view === "detail") setView("home");
  renderAll();
}

async function restoreSession() {
  setView("home");
  if (!state.token) {
    renderAll();
    await loadOpinions();
    return;
  }
  try {
    const me = await api("/api/me");
    state.anonId = me.anonId;
    state.role = me.role || "";
    state.isAdmin = Boolean(me.isAdmin);
    await loadOpinions();
  } catch {
    clearSession();
    await loadOpinions();
  }
}

els.headerWrite.addEventListener("click", startCreate);
els.backBtn.addEventListener("click", () => setView("home"));

document.querySelectorAll(".nav-btn").forEach((button) => {
  button.addEventListener("click", () => {
    const view = button.dataset.view;
    if (view === "write") {
      startCreate();
      return;
    }
    setView(view);
  });
});

els.topicTabs.addEventListener("click", (event) => {
  const tab = event.target.closest(".tab");
  if (!tab) return;
  if (tab.dataset.sort) state.sort = tab.dataset.sort;
  els.topicTabs.querySelectorAll(".tab").forEach((node) => node.classList.toggle("active", node === tab));
  if (els.topicBar) els.topicBar.classList.toggle("hidden", tab.dataset.mode !== "topic");
  renderFeed();
});

if (els.topicBar) {
  els.topicBar.addEventListener("click", (event) => {
    const chip = event.target.closest(".chip-tab");
    if (!chip) return;
    state.topic = chip.dataset.topic || "all";
    els.topicBar.querySelectorAll(".chip-tab").forEach((node) => node.classList.toggle("active", node === chip));
    renderFeed();
  });
}

if (els.search) {
  els.search.addEventListener("input", () => {
    state.query = els.search.value;
    renderFeed();
  });
}

if (els.myPostsBtn) {
  els.myPostsBtn.addEventListener("click", () => {
    state.topic = "mine";
    state.sort = "new";
    els.topicTabs.querySelectorAll(".tab").forEach((node) => {
      node.classList.toggle("active", node.dataset.mode === "topic");
    });
    if (els.topicBar) {
      els.topicBar.classList.remove("hidden");
      els.topicBar.querySelectorAll(".chip-tab").forEach((node) => {
        node.classList.toggle("active", node.dataset.topic === "mine");
      });
    }
    setView("home");
    renderFeed();
  });
}

els.logout.addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch {
    // ignore
  }
  clearSession();
  state.topic = "all";
  state.query = "";
  state.editingCommentId = "";
  if (els.search) els.search.value = "";
  document.querySelector("#email").value = "";
  fillForm(null);
  showError(els.authError, "");
  showError(els.formError, "");
  renderAll();
  await loadOpinions();
  setView("me");
});

els.authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError(els.authError, "");
  try {
    const data = await api("/api/auth", {
      method: "POST",
      body: JSON.stringify({ email: document.querySelector("#email").value }),
    });
    state.token = data.token;
    state.anonId = data.anonId;
    state.role = data.role || "";
    state.isAdmin = Boolean(data.isAdmin);
    localStorage.setItem("voc_token", data.token);
    renderIdentity();
    await loadOpinions();
    setView("home");
  } catch (error) {
    showError(els.authError, error.message);
  }
});

els.opinionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  showError(els.formError, "");
  if (!state.anonId) {
    setView("me");
    return;
  }
  const payload = {
    ask: document.querySelector("#ask").value,
    others: document.querySelector("#others").value,
    priority: Number(document.querySelector("input[name=\"priority\"]:checked").value),
  };
  try {
    const result = state.editingId
      ? await api(`/api/opinions/${state.editingId}`, { method: "PUT", body: JSON.stringify(payload) })
      : await api("/api/opinions", { method: "POST", body: JSON.stringify(payload) });
    if (result.googleForm?.ok) showError(els.formError, "게시했습니다.", true);
    else if (result.googleForm && !result.googleForm.ok) {
      showError(els.formError, `게시는 됐습니다. 폼 저장 실패: ${result.googleForm.error}`);
    } else {
      showError(els.formError, "게시했습니다.", true);
    }
    state.editingId = "";
    fillForm(null);
    await loadOpinions();
    setView("home");
  } catch (error) {
    showError(els.formError, error.message);
  }
});

function bindBoard(root) {
  root.addEventListener("click", async (event) => {
    const open = event.target.closest("[data-open]");
    if (open) {
      openDetail(open.getAttribute("data-open"));
      return;
    }
    const editButton = event.target.closest(".edit-btn");
    if (editButton) {
      startEdit(editButton.dataset.id);
      return;
    }
    const deleteButton = event.target.closest(".delete-btn");
    if (deleteButton) {
      const target = findItem(deleteButton.dataset.id);
      if (!target || !window.confirm(`${target.numberLabel} 글을 삭제할까요?`)) return;
      await api(`/api/opinions/${target.id}`, { method: "DELETE" });
      state.selectedId = "";
      await loadOpinions();
      setView("home");
      return;
    }
    const star = event.target.closest(".star-btn");
    if (star) {
      if (star.disabled) return;
      await api(`/api/opinions/${star.dataset.id}/rate`, {
        method: "POST",
        body: JSON.stringify({ stars: Number(star.dataset.stars) }),
      });
      await loadOpinions();
      return;
    }
    const vote = event.target.closest(".vote-btn");
    if (vote) {
      if (vote.disabled) return;
      try {
        await api(`/api/opinions/${vote.dataset.id}/vote`, { method: "POST" });
        await loadOpinions();
      } catch (error) {
        alert(error.message);
      }
      return;
    }
    const commentEdit = event.target.closest(".comment-edit-btn");
    if (commentEdit) {
      state.editingCommentId = commentEdit.dataset.commentId;
      renderDetail();
      return;
    }
    const commentDel = event.target.closest(".comment-del");
    if (commentDel) {
      if (!window.confirm("이 댓글을 삭제할까요?")) return;
      await api(`/api/comments/${commentDel.dataset.commentId}`, { method: "DELETE" });
      state.editingCommentId = "";
      await loadOpinions();
    }
  });

  root.addEventListener("submit", async (event) => {
    const editForm = event.target.closest(".comment-edit");
    if (editForm) {
      event.preventDefault();
      const input = editForm.querySelector("input[name='body']");
      await api(`/api/comments/${editForm.dataset.commentId}`, {
        method: "PUT",
        body: JSON.stringify({ body: input.value }),
      });
      state.editingCommentId = "";
      await loadOpinions();
      return;
    }
    const form = event.target.closest(".comment-form");
    if (!form) return;
    event.preventDefault();
    const input = form.querySelector("input[name='body']");
    await api(`/api/opinions/${form.dataset.id}/comments`, {
      method: "POST",
      body: JSON.stringify({ body: input.value }),
    });
    input.value = "";
    await loadOpinions();
  });
}

bindBoard(els.feed);
bindBoard(els.detail);
if (els.myPostList) bindBoard(els.myPostList);
if (els.myCommentList) bindBoard(els.myCommentList);
restoreSession();
