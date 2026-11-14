import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
const shots = "../docs/screenshots";

test("scene, playback, cutaway, comparison, twin, faults and learning", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  mkdirSync(shots, { recursive: true });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "The heat exchanger" }),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.locator("canvas")).toHaveCount(1);
  await page.screenshot({ path: `${shots}/simulation.png`, fullPage: true });
  await page.getByRole("button", { name: "Cutaway" }).click();
  await page.getByRole("button", { name: "Cutaway" }).click();
  await page.screenshot({ path: `${shots}/cutaway.png`, fullPage: true });
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect(page.getByText("RUNNING", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(page.getByText("PAUSED", { exact: false })).toBeVisible();
  await page
    .getByRole("button", { name: "PID Comparison", exact: true })
    .click();
  await page.getByRole("button", { name: "APPLY & RESTART" }).click();
  await expect(
    page.getByRole("button", { name: "RUN SIMULATION" }),
  ).toBeVisible({ timeout: 30000 });
  await page.screenshot({ path: `${shots}/comparison.png`, fullPage: true });
  await page.getByRole("button", { name: "Digital Twin", exact: true }).click();
  await page.screenshot({ path: `${shots}/twin.png`, fullPage: true });
  await page
    .getByRole("button", { name: "Fault Laboratory", exact: true })
    .click();
  await page
    .locator("select")
    .filter({ has: page.locator('option[value="sensor_bias"]') })
    .selectOption("sensor_bias");
  await page.getByRole("button", { name: "APPLY & RESTART" }).click();
  await expect(
    page.getByRole("button", { name: "RUN SIMULATION" }),
  ).toBeVisible({ timeout: 30000 });
  await page.getByLabel("Simulation timeline").fill("140");
  await expect(page.getByText("Residual alarm", { exact: true })).toBeVisible();
  await page.screenshot({ path: `${shots}/fault.png`, fullPage: true });
  await page.getByRole("button", { name: "Learn", exact: true }).click();
  await expect(page.getByText("Meet the exchanger")).toBeVisible();
  await page.screenshot({ path: `${shots}/learning.png`, fullPage: true });
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  expect((await download).suggestedFilename()).toContain(".csv");
  expect(errors).toEqual([]);
});

test("new setpoint uses authoritative valve dynamics and reset freezes playback", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "The heat exchanger" }),
  ).toBeVisible({ timeout: 30000 });
  await page.getByLabel("Setpoint").fill("62");
  const responsePromise = page.waitForResponse(
    (r) => r.url().includes("/api/run") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "APPLY & RESTART" }).click();
  const body = await (await responsePromise).json();
  const samples = body.runs.PID.samples;
  expect(samples[31].command).toBeGreaterThan(samples[29].command);
  expect(samples[31].valve).not.toBeCloseTo(samples[31].command, 3);
  expect(samples[100].tc).toBeGreaterThan(samples[29].tc);
  await page.screenshot({
    path: "../docs/screenshots/pid.png",
    fullPage: true,
  });
  await page.getByLabel("Simulation timeline").fill("100");
  await page.getByRole("button", { name: "Reset playback" }).click();
  await expect(page.getByLabel("Simulation timeline")).toHaveValue("0");
  await page.getByTitle("Focus selected equipment").click();
  await page.getByTitle("Reset camera").click();
  await page.getByRole("button", { name: "SHOW VALVE OUTPUT" }).click();
});

test("mobile layout keeps scene and controls reachable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "The heat exchanger" }),
  ).toBeVisible({ timeout: 30000 });
  await expect(page.locator("canvas")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "RUN SIMULATION" }),
  ).toBeVisible();
  await page.screenshot({
    path: "../docs/screenshots/mobile.png",
    fullPage: true,
  });
});
