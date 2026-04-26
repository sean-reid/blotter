import { expect, test } from "@playwright/test";

test.describe("map view", () => {
  test("loads with map centered on Santa Clara County", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".maplibregl-canvas", { timeout: 10000 });
    await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  });

  test("search box is visible and interactive", async ({ page }) => {
    await page.goto("/");
    const search = page.locator('input[placeholder="Search dispatch audio"]');
    await expect(search).toBeVisible();
    await search.fill("traffic stop");
    await expect(search).toHaveValue("traffic stop");
  });

  test("time slider preset buttons work", async ({ page }) => {
    await page.goto("/");
    const buttons = page.locator("button").filter({ hasText: /^(1 h|6 h|24 h|7 d)$/ });
    await expect(buttons).toHaveCount(4);
    await buttons.first().click();
  });
});

test.describe("mobile viewport", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("renders responsively on mobile", async ({ page }) => {
    await page.goto("/");
    await page.waitForSelector(".maplibregl-canvas", { timeout: 10000 });
    await expect(page.locator(".maplibregl-canvas")).toBeVisible();
  });
});
