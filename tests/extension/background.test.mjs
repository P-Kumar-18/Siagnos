// Runs extension/background.js UNMODIFIED with stubbed chrome, fetch and config.js.
import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const BACKGROUND_SRC = path.join(here, "../../extension/background.js");

let listener, stored, fetches, fetchImpl;

async function loadBackground() {
  // config.js is not part of what was provided, so a stub supplies the base URL.
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "siagnos-bg-"));
  fs.copyFileSync(BACKGROUND_SRC, path.join(dir, "background.js"));
  fs.writeFileSync(path.join(dir, "config.js"), 'export const SIAGNOS_CONFIG = { API_BASE_URL: "http://127.0.0.1:8000" };');
  listener = null; stored = {}; fetches = [];
  globalThis.chrome = {
    runtime: { onMessage: { addListener: (fn) => { listener = fn; } } },
    storage: { local: { set: (obj, cb) => { Object.assign(stored, obj); cb?.(); } } },
  };
  globalThis.fetch = async (url, init) => { fetches.push({ url, init }); return fetchImpl(url, init); };
  console.log = () => {}; console.error = () => {};
  await import(pathToFileURL(path.join(dir, "background.js")).href + `?t=${Date.now()}`);
}

const sender = { tab: { id: 17, windowId: 3 } };
const EVENT = { fic_id: 1, chapter_number: 2, event_type: "progress", destination_chapter: 3, timestamp: "2026-01-01T10:00:00Z" };
const settle = () => new Promise((r) => setTimeout(r, 10));

beforeEach(async () => {
  fetchImpl = async () => ({ ok: true, status: 200, text: async () => "{}" });
  await loadBackground();
});

test("TRACKING_EVENT is POSTed as JSON to /tracker/event with the original fields intact", async () => {
  listener({ type: "TRACKING_EVENT", data: EVENT }, sender);
  await settle();
  assert.equal(fetches.length, 1);
  assert.equal(fetches[0].url, "http://127.0.0.1:8000/tracker/event");
  assert.equal(fetches[0].init.method, "POST");
  const body = JSON.parse(fetches[0].init.body);
  for (const [k, v] of Object.entries(EVENT)) assert.equal(body[k], v, k);
  assert.equal(body.tab_id, 17);
  assert.equal(body.window_id, 3);
});

test("PAGE_STATE is stored locally and never sent to the backend", async () => {
  listener({ type: "PAGE_STATE", data: { fic_id: 1, chapter_number: 2 } }, sender);
  await settle();
  assert.equal(fetches.length, 0);
  assert.equal(stored.latest_page_state.fic_id, 1);
});

test("a failed request (network error or HTTP error) does not throw out of the listener", async () => {
  fetchImpl = async () => { throw new TypeError("fetch failed"); };
  listener({ type: "TRACKING_EVENT", data: EVENT }, sender);
  await settle();
  fetchImpl = async () => ({ ok: false, status: 500, text: async () => "boom" });
  listener({ type: "TRACKING_EVENT", data: EVENT }, sender);
  await settle();
  assert.equal(fetches.length, 2);
});

test("unrelated messages are ignored", async () => {
  listener({ type: "SOMETHING_ELSE", data: {} }, sender);
  await settle();
  assert.equal(fetches.length, 0);
});
