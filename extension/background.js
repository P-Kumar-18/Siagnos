import { SIAGNOS_CONFIG } from "./config.js";

const TRACKING_ENDPOINT =
  `${SIAGNOS_CONFIG.API_BASE_URL}/tracker/event`;

chrome.runtime.onMessage.addListener((message, sender) => {
  if (message?.type === "PAGE_STATE") {
    const pageState = {
      ...message.data,
      tab_id: sender.tab?.id ?? null,
      window_id: sender.tab?.windowId ?? null,
    };

    chrome.storage.local.set(
      { latest_page_state: pageState },
      () => {
        console.log("Siagnos page state:", pageState);
      }
    );

    return;
  }

  if (message?.type === "TRACKING_EVENT") {
    const event = {
      ...message.data,
      tab_id: sender.tab?.id ?? null,
      window_id: sender.tab?.windowId ?? null,
    };

    chrome.storage.local.set(
      { latest_tracking_event: event },
      () => {
        console.log("Siagnos tracking event:", event);
      }
    );

    sendTrackingEvent(event);
  }
});


async function sendTrackingEvent(event) {
  try {
    const response = await fetch(TRACKING_ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(event),
    });

    const responseText = await response.text();

    if (!response.ok) {
      console.error(
        "Siagnos tracker API error:",
        response.status,
        responseText
      );
      return;
    }

    console.log(
      "Siagnos tracker API response:",
      response.status,
      responseText
    );
  } catch (error) {
    console.error(
      "Siagnos tracker API request failed:",
      error
    );
  }
}