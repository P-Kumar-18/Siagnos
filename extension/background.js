chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type !== "PAGE_STATE") {
    return;
  }

  const pageState = {
    ...message.data,
    tab_id: sender.tab?.id ?? null,
    window_id: sender.tab?.windowId ?? null,
  };

  chrome.storage.local.set({ latest_page_state: pageState }, () => {
    console.log("Siagnos page state:", pageState);
  });
});
