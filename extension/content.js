let hasReportedThisDocument = false;

function getPageState() {
  const path = window.location.pathname;

  // Multi-chapter work: /works/<fic_id>/chapters/<chapter_id>
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

  // Single-chapter work: /works/<fic_id>
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

// A normal visible page is reported once.
reportVisiblePage();

// A prerendered/hidden page is reported when it becomes visible.
// The per-document flag prevents this from producing a second report.
document.addEventListener("visibilitychange", reportVisiblePage);

if ("prerendering" in document) {
  document.addEventListener("prerenderingchange", reportVisiblePage, {
    once: true,
  });
}
