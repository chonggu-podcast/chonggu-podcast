// Screenshots of real news pages (2026-10-05, 朋友反馈「要真实的新闻截图」). Phone-width page, top of the article.
// node news_shot.mjs key url [key url ...]  -> news/<key>_full.png   (cropping to the headline happens afterwards)
import puppeteer from 'puppeteer-core'
const args = process.argv.slice(2)
const b = await puppeteer.launch({ executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', headless: 'new' })
for (let i = 0; i < args.length; i += 2) {
  const [key, url] = [args[i], args[i + 1]]
  const p = await b.newPage()
  await p.setUserAgent('Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1')
  await p.setViewport({ width: 430, height: 1100, deviceScaleFactor: 2.5, isMobile: true, hasTouch: true })
  try {
    await p.goto(url, { waitUntil: 'domcontentloaded', timeout: 45000 })
    await new Promise((r) => setTimeout(r, 4000))
    // hide overlays only (consent banners, app-download bars, sticky ads): nothing is clicked or accepted
    await p.evaluate(() => {
      for (const el of document.querySelectorAll('body *')) {
        const cs = getComputedStyle(el)
        if ((cs.position === 'fixed' || cs.position === 'sticky') && el.getBoundingClientRect().height < 700) el.style.setProperty('display', 'none', 'important')
      }
      window.scrollTo(0, 0)
    })
    await new Promise((r) => setTimeout(r, 600))
    const h1 = await p.evaluate(() => { const h = document.querySelector('h1'); if (!h) return null; const r = h.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, text: h.innerText.slice(0, 60) } })
    await p.screenshot({ path: `news/${key}_full.png`, clip: { x: 0, y: 0, width: 430, height: 1100 } })
    console.log(key, 'ok', JSON.stringify(h1))
  } catch (e) { console.log(key, 'FAIL', e.message.slice(0, 120)) }
  await p.close()
}
await b.close()
