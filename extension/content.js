let hasReportedThisDocument = false;
let leaveEventSent = false;
let pendingNavigation = false;

function getPageState() {
  const path = window.location.pathname;

  // Multi-chapter work:
  // /works/<fic_id>/chapters/<chapter_id>
  const chapterMatch = path.match(/^\/works\/(\d+)\/chapters\/(\d+)/);

  if (chapterMatch) {
    const [, ficId, chapterId] = chapterMatch;

    return {
      fic_id: Number(ficId),
      chapter_id: Number(chapterId),
      chapter_number: getChapterNumber(),
      url: window.location.href,
      timestamp: new Date().toISOString(),
    };
  }

  // Single-chapter work:
  // /works/<fic_id>
  const workMatch = path.match(/^\/works\/(\d+)\/?$/);

  if (workMatch) {
    const [, ficId] = workMatch;

    return {
      fic_id: Number(ficId),
      chapter_id: null,
      chapter_number: 1,
      url: window.location.href,
      timestamp: new Date().toISOString(),
    };
  }

  return null;
}

function getChapterNumber() {
  const chapterSelect = document.querySelector("#selected_id");
  const selectedOption = chapterSelect?.selectedOptions?.[0];

  if (chapterSelect && selectedOption) {
    const options = Array.from(chapterSelect.options);
    const selectedIndex = options.indexOf(selectedOption);

    if (selectedIndex !== -1) {
      return selectedIndex + 1;
    }
  }

  // A chapter URL without the chapter selector is treated as chapter 1.
  return 1;
}

function reportVisiblePage() {
  if (hasReportedThisDocument) {
    return;
  }

  if (document.visibilityState !== "visible") {
    return;
  }

  if ("prerendering" in document && document.prerendering) {
    return;
  }

  const pageState = getPageState();

  if (!pageState) {
    return;
  }

  hasReportedThisDocument = true;

  chrome.runtime.sendMessage({
    type: "PAGE_STATE",
    data: pageState,
  });
}

function getDestinationChapter(link) {
  if (!link) {
    return null;
  }

  const currentState = getPageState();

  if (!currentState) {
    return null;
  }

  let destinationUrl;

  try {
    destinationUrl = new URL(link.href, window.location.origin);
  } catch {
    return null;
  }

  const match = destinationUrl.pathname.match(
    /^\/works\/(\d+)\/chapters\/(\d+)/
  );

  if (!match) {
    return null;
  }

  const ficId = Number(match[1]);
  const chapterId = Number(match[2]);

  if (ficId !== currentState.fic_id) {
    return null;
  }

  /*
   * AO3's chapter selector can expose either:
   *
   *   1. the chapter ID directly as option.value
   *   2. a URL containing the chapter ID
   *
   * Support both forms.
   */
  const chapterSelect = document.querySelector("#selected_id");

  if (chapterSelect) {
    const options = Array.from(chapterSelect.options);

    for (let index = 0; index < options.length; index++) {
      const option = options[index];

      if (!option.value) {
        continue;
      }

      // Case 1: AO3 gives us the chapter ID directly.
      if (String(option.value) === String(chapterId)) {
        return {
          fic_id: ficId,
          chapter_id: chapterId,
          chapter_number: index + 1,
        };
      }

      // Case 2: AO3 gives us a URL containing the chapter ID.
      try {
        const optionUrl = new URL(
          option.value,
          window.location.origin
        );

        const optionMatch = optionUrl.pathname.match(
          /^\/works\/(\d+)\/chapters\/(\d+)/
        );

        if (
          optionMatch &&
          Number(optionMatch[1]) === ficId &&
          Number(optionMatch[2]) === chapterId
        ) {
          return {
            fic_id: ficId,
            chapter_id: chapterId,
            chapter_number: index + 1,
          };
        }
      } catch {
        // Ignore values that are not valid URLs.
      }
    }
  }

  /*
   * AO3's explicit next/previous links give us enough
   * information to resolve adjacent chapter navigation.
   */
  const linkText = link.textContent?.trim().toLowerCase();

  if (linkText === "next chapter") {
    return {
      fic_id: ficId,
      chapter_id: chapterId,
      chapter_number: currentState.chapter_number + 1,
    };
  }

  if (linkText === "previous chapter") {
    return {
      fic_id: ficId,
      chapter_id: chapterId,
      chapter_number: Math.max(
        1,
        currentState.chapter_number - 1
      ),
    };
  }

  return null;
}

function sendProgressEvent(destination) {
  if (leaveEventSent) {
    return;
  }

  const currentState = getPageState();

  if (!currentState) {
    return;
  }

  leaveEventSent = true;
  pendingNavigation = true;

  const event = {
    fic_id: currentState.fic_id,
    chapter_number: currentState.chapter_number,
    event_type: "progress",
    destination_chapter: destination.chapter_number,
    timestamp: new Date().toISOString(),
  };

  chrome.runtime.sendMessage({
    type: "TRACKING_EVENT",
    data: event,
  });

  console.log("Siagnos navigation detected:", event);
}

function handleChapterNavigation(event) {
  if (event.defaultPrevented) {
    return;
  }

  if (event.button !== 0) {
    return;
  }

  if (
    event.ctrlKey ||
    event.metaKey ||
    event.shiftKey ||
    event.altKey
  ) {
    return;
  }

  const link = event.target.closest("a");

  if (!link) {
    return;
  }

  const destination = getDestinationChapter(link);

  if (!destination) {
    return;
  }

  sendProgressEvent(destination);
}

function sendCloseEvent() {
  /*
   * A known chapter navigation is not a close event.
   */
  if (leaveEventSent || pendingNavigation) {
    return;
  }

  const currentState = getPageState();

  if (!currentState) {
    return;
  }

  leaveEventSent = true;

  const event = {
    fic_id: currentState.fic_id,
    chapter_number: currentState.chapter_number,
    event_type: "close",
    timestamp: new Date().toISOString(),
  };

  chrome.runtime.sendMessage({
    type: "TRACKING_EVENT",
    data: event,
  });

  console.log("Siagnos close detected:", event);
}

// Report the currently visible page once.
reportVisiblePage();

// Handle pages that become visible after being prerendered/hidden.
document.addEventListener(
  "visibilitychange",
  reportVisiblePage
);

if ("prerendering" in document) {
  document.addEventListener(
    "prerenderingchange",
    reportVisiblePage,
    { once: true }
  );
}

/*
 * Capture the navigation before AO3/browser navigation
 * begins unloading the current document.
 */
document.addEventListener(
  "click",
  (event) => {
    const link = event.target.closest("a");

    console.log("Siagnos click:", {
      target: event.target,
      link: link,
      href: link?.href ?? null,
      rel: link?.getAttribute("rel") ?? null,
      text: link?.textContent?.trim() ?? null,
    });

    handleChapterNavigation(event);
  },
  true
);

/*
 * If the document leaves without a known chapter navigation,
 * treat it as a close.
 */
window.addEventListener(
  "pagehide",
  sendCloseEvent
);