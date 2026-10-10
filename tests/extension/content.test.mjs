// Runs extension/content.js UNMODIFIED inside jsdom with a recording chrome.runtime.
//
// Covers: event_type progress vs close, destination resolution (selector, explicit
// Next/Previous), no false close after a recognised navigation, Browser Back being
// unsupported (no destination is ever inferred, it is just a close), and the payload
// the backend's TrackingEvent model expects.
import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM, VirtualConsole } from "jsdom";

const here = path.dirname(fileURLToPath(import.meta.url));
const CONTENT_JS = fs.readFileSync(path.join(here, "../../extension/content.js"), "utf8");

// chapterIds: AO3 chapter ids in order; `selected` is the 1-based current position.
function openPage({ url, chapterIds = null, selected = 1, links = [] }) {
  const options = chapterIds
    ? chapterIds
        .map((id, i) => `<option value="${id}"${i + 1 === selected ? " selected" : ""}>${i + 1}. c</option>`)
        .join("")
    : "";
  const select = chapterIds ? `<select id="selected_id">${options}</select>` : "";
  const anchors = links.map((l) => `<a id="${l.id}" href="${l.href}">${l.text}</a>`).join("");

  const dom = new JSDOM(`<!doctype html><body>${select}${anchors}</body>`, {
    url,
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole: new VirtualConsole(), // silence the script's console.log
  });
  const { window } = dom;
  const messages = [];
  window.chrome = { runtime: { sendMessage: (m) => messages.push(m) } };
  // Stop jsdom attempting a real navigation after the click.
  window.document.addEventListener("click", (e) => e.preventDefault());
  window.eval(CONTENT_JS);

  const click = (id, init = {}) =>
    window.document.getElementById(id).dispatchEvent(
      new window.MouseEvent("click", { bubbles: true, cancelable: true, button: 0, ...init })
    );
  const leave = () => window.dispatchEvent(new window.Event("pagehide"));
  const events = () => messages.filter((m) => m.type === "TRACKING_EVENT").map((m) => m.data);
  return { window, messages, click, leave, events };
}

const FIC = 777;
const IDS = [9001, 9002, 9003, 9004, 9005];
const chapterUrl = (n) => `https://archiveofourown.org/works/${FIC}/chapters/${IDS[n - 1]}`;

test("page state is reported once for a visible chapter page", () => {
  const p = openPage({ url: chapterUrl(2), chapterIds: IDS, selected: 2 });
  const states = p.messages.filter((m) => m.type === "PAGE_STATE");
  assert.equal(states.length, 1);
  assert.equal(states[0].data.fic_id, FIC);
  assert.equal(states[0].data.chapter_number, 2);
});

test("non-work AO3 pages produce no events at all", () => {
  const p = openPage({ url: "https://archiveofourown.org/works/search" });
  p.leave();
  assert.equal(p.messages.length, 0);
});

test("explicit Next Chapter click -> one progress event to N+1 (selector resolves the id)", () => {
  const p = openPage({
    url: chapterUrl(2), chapterIds: IDS, selected: 2,
    links: [{ id: "next", href: chapterUrl(3), text: "Next Chapter →" }],
  });
  p.click("next");
  const [e] = p.events();
  assert.equal(p.events().length, 1);
  assert.equal(e.event_type, "progress");
  assert.equal(e.fic_id, FIC);
  assert.equal(e.chapter_number, 2);
  assert.equal(e.destination_chapter, 3);
  assert.ok(!Number.isNaN(Date.parse(e.timestamp)));
});

test("explicit Previous Chapter click -> progress event to N-1", () => {
  const p = openPage({
    url: chapterUrl(4), chapterIds: IDS, selected: 4,
    links: [{ id: "prev", href: chapterUrl(3), text: "← Previous Chapter" }],
  });
  p.click("prev");
  const [e] = p.events();
  assert.equal(e.event_type, "progress");
  assert.equal(e.chapter_number, 4);
  assert.equal(e.destination_chapter, 3);
});

test("chapter-index jump resolves the destination position through the selector", () => {
  const p = openPage({
    url: chapterUrl(1), chapterIds: IDS, selected: 1,
    links: [{ id: "jump", href: chapterUrl(5), text: "5. Chapter five" }],
  });
  p.click("jump");
  const [e] = p.events();
  assert.equal(e.event_type, "progress");
  assert.equal(e.destination_chapter, 5);
});

test("a recognised chapter navigation is not followed by a false close", () => {
  const p = openPage({
    url: chapterUrl(2), chapterIds: IDS, selected: 2,
    links: [{ id: "next", href: chapterUrl(3), text: "Next Chapter" }],
  });
  p.click("next");
  p.leave(); // pagehide fires as the page unloads
  assert.deepEqual(p.events().map((e) => e.event_type), ["progress"]);
});

test("leaving without a known navigation -> exactly one close, no destination", () => {
  const p = openPage({ url: chapterUrl(3), chapterIds: IDS, selected: 3 });
  p.leave();
  p.leave();
  const events = p.events();
  assert.equal(events.length, 1);
  assert.equal(events[0].event_type, "close");
  assert.equal(events[0].chapter_number, 3);
  assert.ok(!("destination_chapter" in events[0]));
});

test("Browser Back is unsupported: no destination is inferred, it is only a close", () => {
  const p = openPage({ url: chapterUrl(4), chapterIds: IDS, selected: 4 });
  p.window.dispatchEvent(new p.window.PopStateEvent("popstate")); // history navigation
  p.leave();
  const events = p.events();
  assert.deepEqual(events.map((e) => e.event_type), ["close"]);
  assert.ok(!events.some((e) => "destination_chapter" in e));
});

test("modified clicks (ctrl/meta/shift/alt) are ignored, the later leave is a close", () => {
  for (const mod of [{ ctrlKey: true }, { metaKey: true }, { shiftKey: true }, { altKey: true }]) {
    const p = openPage({
      url: chapterUrl(2), chapterIds: IDS, selected: 2,
      links: [{ id: "next", href: chapterUrl(3), text: "Next Chapter" }],
    });
    p.click("next", mod);
    assert.equal(p.events().length, 0, JSON.stringify(mod));
    p.leave();
    assert.deepEqual(p.events().map((e) => e.event_type), ["close"]);
  }
});

test("links to non-chapter pages or to another fic are not chapter navigation", () => {
  const p = openPage({
    url: chapterUrl(2), chapterIds: IDS, selected: 2,
    links: [
      { id: "profile", href: "https://archiveofourown.org/users/someone", text: "someone" },
      { id: "other", href: "https://archiveofourown.org/works/888/chapters/1", text: "Next Chapter" },
    ],
  });
  p.click("profile");
  p.click("other");
  assert.equal(p.events().length, 0);
  p.leave();
  assert.deepEqual(p.events().map((e) => e.event_type), ["close"]);
});

test("only the first leave event is sent per document", () => {
  const p = openPage({
    url: chapterUrl(2), chapterIds: IDS, selected: 2,
    links: [
      { id: "next", href: chapterUrl(3), text: "Next Chapter" },
      { id: "prev", href: chapterUrl(1), text: "Previous Chapter" },
    ],
  });
  p.click("next");
  p.click("prev");
  assert.equal(p.events().length, 1);
  assert.equal(p.events()[0].destination_chapter, 3);
});

test("single-chapter work reports chapter 1 and closes with a close event", () => {
  const p = openPage({ url: `https://archiveofourown.org/works/${FIC}` });
  p.leave();
  const [e] = p.events();
  assert.equal(e.event_type, "close");
  assert.equal(e.chapter_number, 1);
  assert.equal(e.fic_id, FIC);
});
