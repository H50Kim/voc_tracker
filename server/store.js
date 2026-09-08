import { randomUUID } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const emptyDb = () => ({
  users: [],
  opinions: [],
  votes: [],
  comments: [],
  ratings: [],
  nextNumber: 1,
});

export function createStore(filePath) {
  let db = emptyDb();
  let writeChain = Promise.resolve();

  async function load() {
    await mkdir(path.dirname(filePath), { recursive: true });
    try {
      const raw = await readFile(filePath, "utf8");
      const parsed = JSON.parse(raw);
      db = {
        users: Array.isArray(parsed.users) ? parsed.users : [],
        opinions: Array.isArray(parsed.opinions) ? parsed.opinions : [],
        votes: Array.isArray(parsed.votes) ? parsed.votes : [],
        comments: Array.isArray(parsed.comments) ? parsed.comments : [],
        ratings: Array.isArray(parsed.ratings) ? parsed.ratings : [],
        nextNumber: Number(parsed.nextNumber) > 0 ? Number(parsed.nextNumber) : 1,
      };
      assignMissingNumbers();
      await persist();
    } catch (error) {
      if (error && error.code === "ENOENT") {
        await persist();
        return;
      }
      throw error;
    }
  }

  function assignMissingNumbers() {
    let max = 0;
    for (const opinion of db.opinions) {
      const number = Number(opinion.number);
      if (Number.isFinite(number) && number > max) max = number;
    }
    let next = Math.max(max + 1, Number(db.nextNumber) || 1);
    const ordered = [...db.opinions].sort(
      (a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
    );
    for (const opinion of ordered) {
      const number = Number(opinion.number);
      if (!Number.isFinite(number) || number < 1) {
        opinion.number = next;
        next += 1;
      }
    }
    db.nextNumber = next;
  }

  function takeNumber() {
    assignMissingNumbers();
    const number = db.nextNumber;
    db.nextNumber += 1;
    return number;
  }

  function persist() {
    writeChain = writeChain.then(() =>
      writeFile(filePath, JSON.stringify(db, null, 2), "utf8"),
    );
    return writeChain;
  }

  return {
    load,
    findUserByEmailHash(emailHash) {
      return db.users.find((user) => user.emailHash === emailHash) ?? null;
    },
    findUserById(id) {
      return db.users.find((user) => user.id === id) ?? null;
    },
    async createUser({ emailHash, anonId }) {
      const existing = db.users.find((user) => user.emailHash === emailHash);
      if (existing) return existing;
      const user = {
        id: randomUUID(),
        emailHash,
        anonId,
        createdAt: new Date().toISOString(),
      };
      db.users.push(user);
      await persist();
      return user;
    },
    listOpinions() {
      return [...db.opinions].sort(
        (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
      );
    },
    findOpinionById(id) {
      return db.opinions.find((item) => item.id === id) ?? null;
    },
    findOpinionByAuthor(userId) {
      return db.opinions.find((item) => item.userId === userId) ?? null;
    },
    listOpinionsByAuthor(userId) {
      return db.opinions.filter((item) => item.userId === userId);
    },
    findOpinionByFormKey(formKey) {
      return db.opinions.find((item) => item.formKey === formKey) ?? null;
    },
    async upsertFormOpinion({ userId, ask, others, priority, formKey, createdAt }) {
      const existing =
        db.opinions.find((item) => item.formKey === formKey) ??
        db.opinions.find((item) => item.userId === userId && item.source === "google");
      if (existing) {
        existing.ask = ask;
        existing.others = others;
        existing.priority = priority;
        existing.source = "google";
        existing.formKey = formKey;
        existing.updatedAt = new Date().toISOString();
        if (createdAt && !existing.createdAt) existing.createdAt = createdAt;
        await persist();
        return existing;
      }
      const opinion = {
        id: randomUUID(),
        number: takeNumber(),
        userId,
        ask,
        others,
        priority,
        source: "google",
        formKey,
        createdAt: createdAt || new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      db.opinions.push(opinion);
      await persist();
      return opinion;
    },
    async createOpinion({ userId, ask, others, priority, source = "app", formKey = "" }) {
      const id = randomUUID();
      const opinion = {
        id,
        number: takeNumber(),
        userId,
        ask,
        others,
        priority,
        source,
        formKey: formKey || `app:${userId}:${id}`,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      db.opinions.push(opinion);
      await persist();
      return opinion;
    },
    async updateOpinion(id, { ask, others, priority }) {
      const opinion = db.opinions.find((item) => item.id === id);
      if (!opinion) return null;
      opinion.ask = ask;
      opinion.others = others;
      opinion.priority = priority;
      opinion.updatedAt = new Date().toISOString();
      await persist();
      return opinion;
    },
    async deleteOpinion(id) {
      const index = db.opinions.findIndex((item) => item.id === id);
      if (index < 0) return false;
      db.opinions.splice(index, 1);
      db.votes = db.votes.filter((vote) => vote.opinionId !== id);
      db.comments = db.comments.filter((comment) => comment.opinionId !== id);
      db.ratings = db.ratings.filter((rating) => rating.opinionId !== id);
      await persist();
      return true;
    },
    listComments(opinionId) {
      return db.comments
        .filter((comment) => comment.opinionId === opinionId)
        .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
    },
    findCommentById(id) {
      return db.comments.find((comment) => comment.id === id) ?? null;
    },
    async addComment({ opinionId, userId, body }) {
      const comment = {
        id: randomUUID(),
        opinionId,
        userId,
        body,
        createdAt: new Date().toISOString(),
      };
      db.comments.push(comment);
      await persist();
      return comment;
    },
    async updateComment(id, body) {
      const comment = db.comments.find((item) => item.id === id);
      if (!comment) return null;
      comment.body = body;
      comment.updatedAt = new Date().toISOString();
      await persist();
      return comment;
    },
    async deleteComment(id) {
      const index = db.comments.findIndex((comment) => comment.id === id);
      if (index < 0) return false;
      db.comments.splice(index, 1);
      await persist();
      return true;
    },
    listRatings(opinionId) {
      return db.ratings.filter((rating) => rating.opinionId === opinionId);
    },
    findRating(userId, opinionId) {
      return (
        db.ratings.find(
          (rating) => rating.userId === userId && rating.opinionId === opinionId,
        ) ?? null
      );
    },
    async upsertRating(userId, opinionId, stars) {
      const existing = db.ratings.find(
        (rating) => rating.userId === userId && rating.opinionId === opinionId,
      );
      const now = new Date().toISOString();
      if (existing) {
        existing.stars = stars;
        existing.updatedAt = now;
        await persist();
        return existing;
      }
      const rating = {
        id: randomUUID(),
        userId,
        opinionId,
        stars,
        createdAt: now,
        updatedAt: now,
      };
      db.ratings.push(rating);
      await persist();
      return rating;
    },
    findVote(userId, opinionId) {
      return (
        db.votes.find(
          (vote) => vote.userId === userId && vote.opinionId === opinionId,
        ) ?? null
      );
    },
    countVotes(opinionId) {
      return db.votes.filter((vote) => vote.opinionId === opinionId).length;
    },
    async addVote(userId, opinionId) {
      const vote = {
        id: randomUUID(),
        userId,
        opinionId,
        createdAt: new Date().toISOString(),
      };
      db.votes.push(vote);
      await persist();
      return vote;
    },
  };
}
