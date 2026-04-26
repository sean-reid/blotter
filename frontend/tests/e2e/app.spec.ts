import { expect, test } from "@playwright/test";

test.describe("map view", () => {
  test("loads with map canvas visible", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".maplibregl-canvas", { timeout: 10000 });
    await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  });

  test("search box is visible and interactive", async ({ page }) => {
    await page.goto("/");
    const search = page.locator('input[placeholder="Search dispatch audio..."]');
    await expect(search).toBeVisible();
    await search.fill("traffic stop");
    await expect(search).toHaveValue("traffic stop");
  });

  test("search box has clear button when filled", async ({ page }) => {
    await page.goto("/");
    const search = page.locator('input[placeholder="Search dispatch audio..."]');
    await search.fill("test query");
    const clearBtn = page.locator("button").filter({ has: page.locator("svg") }).last();
    await expect(clearBtn).toBeVisible();
  });

  test("about link opens modal", async ({ page }) => {
    await page.goto("/");
    await page.getByText("About").click();
    await expect(page.getByText("About Blotter")).toBeVisible();
    await expect(page.getByText("How it works")).toBeVisible();
  });

  test("about modal closes on escape", async ({ page }) => {
    await page.goto("/");
    await page.getByText("About").click();
    await expect(page.getByText("About Blotter")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(page.getByText("About Blotter")).not.toBeVisible();
  });

  test("blotter title is displayed", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("blotter")).toBeVisible();
  });
});

test.describe("transcript search", () => {
  test("search triggers transcript list when results exist", async ({ page }) => {
    await page.route("**/api/query", async (route) => {
      const body = route.request().postData() || "";
      if (body.includes("scanner_transcripts")) {
        await route.fulfill({
          status: 200,
          contentType: "text/plain",
          body: JSON.stringify({
            feed_id: "20296",
            feed_name: "Test Feed",
            archive_ts: "2026-04-26 12:00:00.000",
            duration_ms: 60000,
            audio_url: "/audio-data/test.wav",
            transcript: "code 3 traffic stop on Main Street",
            segments: "[]",
            tags: "code 3",
          }),
        });
      } else {
        await route.fulfill({ status: 200, contentType: "text/plain", body: "" });
      }
    });

    await page.goto("/");
    const search = page.locator('input[placeholder="Search dispatch audio..."]');
    await search.fill("traffic");
    await expect(page.getByText("Transcripts (1)")).toBeVisible({ timeout: 5000 });
    await expect(page.getByText("Test Feed")).toBeVisible();
  });

  test("clicking transcript result opens transcript panel", async ({ page }) => {
    await page.route("**/api/query", async (route) => {
      const body = route.request().postData() || "";
      if (body.includes("scanner_transcripts")) {
        await route.fulfill({
          status: 200,
          contentType: "text/plain",
          body: JSON.stringify({
            feed_id: "20296",
            feed_name: "Test Feed",
            archive_ts: "2026-04-26 12:00:00.000",
            duration_ms: 60000,
            audio_url: "",
            transcript: "code 3 traffic stop on Main Street",
            segments: "[]",
            tags: "code 3",
          }),
        });
      } else {
        await route.fulfill({ status: 200, contentType: "text/plain", body: "" });
      }
    });

    await page.goto("/");
    const search = page.locator('input[placeholder="Search dispatch audio..."]');
    await search.fill("traffic");
    await expect(page.getByText("Test Feed")).toBeVisible({ timeout: 5000 });
    await page.getByText("Test Feed").first().click();
    await expect(page.locator("h3").filter({ hasText: "Transcript" })).toBeVisible();
  });
});

test.describe("tags component", () => {
  test("displays police code tags with labels", async ({ page }) => {
    await page.route("**/api/query", async (route) => {
      const body = route.request().postData() || "";
      if (body.includes("scanner_transcripts")) {
        await route.fulfill({
          status: 200,
          contentType: "text/plain",
          body: JSON.stringify({
            feed_id: "20296",
            feed_name: "Test Feed",
            archive_ts: "2026-04-26 12:00:00.000",
            duration_ms: 60000,
            audio_url: "",
            transcript: "code 3 dispatch to Main Street",
            segments: "[]",
            tags: "code 3,10-97",
          }),
        });
      } else {
        await route.fulfill({ status: 200, contentType: "text/plain", body: "" });
      }
    });

    await page.goto("/");
    const search = page.locator('input[placeholder="Search dispatch audio..."]');
    await search.fill("dispatch");
    await expect(page.getByText("Test Feed")).toBeVisible({ timeout: 5000 });
    await page.getByText("Test Feed").first().click();

    const panel = page.locator("[class*='fixed z-50']");
    await expect(panel.getByText("code 3")).toBeVisible();
    await expect(panel.getByText("Emergency")).toBeVisible();
    await expect(panel.getByText("10-97")).toBeVisible();
    await expect(panel.getByText("Arrived at scene")).toBeVisible();
  });
});

test.describe("transcript panel", () => {
  test("shows feed name and close button", async ({ page }) => {
    await page.route("**/api/query", async (route) => {
      const body = route.request().postData() || "";
      if (body.includes("scanner_transcripts")) {
        await route.fulfill({
          status: 200,
          contentType: "text/plain",
          body: JSON.stringify({
            feed_id: "20296",
            feed_name: "Santa Clara PD",
            archive_ts: "2026-04-26 12:00:00.000",
            duration_ms: 60000,
            audio_url: "",
            transcript: "unit responding to call",
            segments: "[]",
            tags: "",
          }),
        });
      } else {
        await route.fulfill({ status: 200, contentType: "text/plain", body: "" });
      }
    });

    await page.goto("/");
    const search = page.locator('input[placeholder="Search dispatch audio..."]');
    await search.fill("responding");
    await expect(page.getByText("Santa Clara PD")).toBeVisible({ timeout: 5000 });
    await page.getByText("Santa Clara PD").first().click();

    const panel = page.locator("[class*='fixed z-50']");
    await expect(panel.locator("h3").filter({ hasText: "Transcript" })).toBeVisible();
    await expect(panel.getByText("Santa Clara PD")).toBeVisible();

    await panel.locator('button[aria-label="Close panel"]').click();
    await expect(panel.locator("h3").filter({ hasText: "Transcript" })).not.toBeVisible();
  });

  test("shows transcript text when no segments", async ({ page }) => {
    await page.route("**/api/query", async (route) => {
      const body = route.request().postData() || "";
      if (body.includes("scanner_transcripts")) {
        await route.fulfill({
          status: 200,
          contentType: "text/plain",
          body: JSON.stringify({
            feed_id: "20296",
            feed_name: "Test Feed",
            archive_ts: "2026-04-26 12:00:00.000",
            duration_ms: 60000,
            audio_url: "",
            transcript: "unit 5 Adam responding to 459 in progress at Elm and Oak",
            segments: "[]",
            tags: "459",
          }),
        });
      } else {
        await route.fulfill({ status: 200, contentType: "text/plain", body: "" });
      }
    });

    await page.goto("/");
    const search = page.locator('input[placeholder="Search dispatch audio..."]');
    await search.fill("responding");
    await expect(page.getByText("Test Feed")).toBeVisible({ timeout: 5000 });
    await page.getByText("Test Feed").first().click();

    const panel = page.locator("[class*='fixed z-50']");
    await expect(
      panel.getByText("unit 5 Adam responding to 459 in progress at Elm and Oak"),
    ).toBeVisible();
  });
});

test.describe("mobile viewport", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("renders responsively on mobile", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".maplibregl-canvas", { timeout: 10000 });
    await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  });

  test("search box works on mobile", async ({ page }) => {
    await page.goto("/");
    const search = page.locator('input[placeholder="Search dispatch audio..."]');
    await expect(search).toBeVisible();
    await search.fill("test");
    await expect(search).toHaveValue("test");
  });
});
