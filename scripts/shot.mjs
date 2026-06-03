import { chromium, devices } from "playwright";

const URL = "http://localhost:18080/?view=table";
const cases = [
  { name: "iphone", width: 390, height: 844 },
  { name: "small", width: 360, height: 800 },
  { name: "tablet", width: 768, height: 1024 },
];

const browser = await chromium.launch();
for (const c of cases) {
  const ctx = await browser.newContext({
    viewport: { width: c.width, height: c.height },
    deviceScaleFactor: 2,
    isMobile: true,
  });
  const page = await ctx.newPage();
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.waitForTimeout(600);

  // overflow detection
  const report = await page.evaluate(() => {
    const docW = document.documentElement.clientWidth;
    const scrollW = document.documentElement.scrollWidth;
    const offenders = [];
    for (const el of document.querySelectorAll("body *")) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (r.right > docW + 1) {
        offenders.push({
          sel: el.tagName.toLowerCase() +
            (el.id ? "#" + el.id : "") +
            (el.className && typeof el.className === "string"
              ? "." + el.className.trim().split(/\s+/).join(".")
              : ""),
          right: Math.round(r.right),
          width: Math.round(r.width),
        });
      }
    }
    return { docW, scrollW, horizontalOverflow: scrollW > docW + 1, offenders };
  });

  console.log(`\n=== ${c.name} (${c.width}px) ===`);
  console.log(`clientWidth=${report.docW} scrollWidth=${report.scrollW} overflow=${report.horizontalOverflow}`);
  // dedupe offenders by selector, keep widest
  const seen = new Map();
  for (const o of report.offenders) {
    const cur = seen.get(o.sel);
    if (!cur || o.right > cur.right) seen.set(o.sel, o);
  }
  [...seen.values()].sort((a, b) => b.right - a.right).slice(0, 12)
    .forEach((o) => console.log(`  right=${o.right} w=${o.width}  ${o.sel}`));

  await page.screenshot({ path: `/tmp/shot-${c.name}.png`, fullPage: false, timeout: 60000 });
  await ctx.close();
}
await browser.close();
console.log("\nscreenshots: /tmp/shot-*.png");
