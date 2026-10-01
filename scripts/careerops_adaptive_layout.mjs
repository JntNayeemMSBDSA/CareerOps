import { createHash } from "node:crypto";
import { chromium } from 'playwright';
import { readFile, writeFile } from 'fs/promises';
import { resolve } from 'path';
import { pathToFileURL } from 'url';

/*
  CAREEROPS ADAPTIVE ONE-PAGE LAYOUT ENGINE

  PURPOSE
  -------
  Take an already-generated resume HTML and solve its typography
  and vertical rhythm for THIS resume's amount of content.

  FIXED:
    - Letter page
    - existing left/right side margin
    - font families
    - section structure
    - bullet style
    - content
    - hyperlinks

  DYNAMIC:
    - top/bottom margin derived independently from approved template geometry
    - body font size
    - entry/date font size
    - contact font size
    - name size
    - line height
    - section spacing
    - job spacing
    - project spacing
    - bullet spacing
    - skills spacing
    - contact -> first section spacing

  HARD FAIL:
    - second page
    - clipped content
    - contact wraps
    - experience header wraps
    - project header wraps
    - education header/date wraps
    - body must shrink below minimum readability
*/

const INPUT = resolve(
  process.argv[2] || 'output/careerops-final.html'
);

const OUTPUT = resolve(
  process.argv[3] || 'output/careerops-adaptive-final.html'
);

const REPORT = resolve(
  process.argv[4] ||
  'data/careerops-engine/runtime/adaptive_layout_report.json'
);

const PAGE_W = 8.5 * 96;
const PAGE_H = 11 * 96;
// Two minimum body lines accommodate native Word pagination differences.
// Both formats keep the approved .50in page margins and the 10.5pt floor.
const WORD_PAGINATION_RESERVE_PX = 2 * 10.5 * 96 / 72 * 1.065;


/* ============================================================
   PROFESSIONAL SAFE RANGES
   ============================================================ */

const BODY_MIN_PT = 10.50;
const BODY_MAX_PT = 12.00;
const BODY_STEP_PT = 0.50;

const ENTRY_MIN_PT = 10.40;
const ENTRY_MAX_PT = 12.20;

const CONTACT_MIN_PT = 9.75;
const CONTACT_MAX_PT = 11.50;

/*
  Existing design hierarchy:
    body  11
    entry 11.5
    name  14
*/
const ENTRY_RATIO = 11.5 / 11;
const NAME_RATIO = 14 / 11;

/*
  First-section separation is proportional to body leading.
  This stays visually consistent if the body font changes.
*/
/*
  Locked visual relationship from the approved reference layout.

  Dynamic in physical size because body leading changes,
  but NOT available to the general rhythm optimizer.
*/
const HEADER_SECTION_GAP_LINES = 1.216;


/* ============================================================
   HELPERS
   ============================================================ */

const ptPx = pt =>
  pt * 96 / 72;

const lerp = (a, b, t) =>
  a + ((b - a) * t);

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}


/* ============================================================
   TYPOGRAPHIC SYSTEM
   ============================================================ */

function metrics({
  bodyPt,
  entryPt,
  contactPt,
  rhythm
}) {
  // Native Word stores font sizes in half points; solve both formats on that grid.
  entryPt=Math.round(entryPt*2)/2;
  contactPt=Math.round(contactPt*2)/2;
  const bodyPx = ptPx(bodyPt);
  const entryPx = ptPx(entryPt);
  const contactPx = ptPx(contactPt);

  const namePt = Math.floor(bodyPt * NAME_RATIO * 2)/2;
  const namePx = ptPx(namePt);

  const bodyLine =
    bodyPx * lerp(1.065, 1.115, rhythm);

  return {
    bodyPt,
    entryPt,
    contactPt,
    namePt,

    bodyPx,
    entryPx,
    contactPx,
    namePx,

    bodyLine,

    entryLine:
      entryPx * 1.055,

    contactLine:
      contactPx * 1.06122449,

    sectionLine:
      bodyPx * 1.055,

    nameLine:
      namePx * 1.035,

    /*
      Contact/address -> first section.
      Proportional, not fixed.
    */
    headerSectionGapPx:
      bodyLine * HEADER_SECTION_GAP_LINES,

    /*
      Elastic vertical rhythm.
      All have bounded professional ranges.
    */
    majorSectionGapPt:
      lerp(1.2, 5.2, rhythm),

    sectionTitleGapPt:
      lerp(0.30, 1.8, rhythm),

    jobGapPt:
      lerp(0.35, 3.8, rhythm),

    projectGapPt:
      lerp(0.35, 3.8, rhythm),

    bulletGapPx:
      lerp(
        bodyLine * 0.055,
        bodyLine * 0.18,
        rhythm
      ),

    skillGapPx:
      lerp(
        bodyLine * 0.05,
        bodyLine * 0.16,
        rhythm
      ),

    certGapPt:
      lerp(0.65, 2.8, rhythm),

    educationGapPt:
      lerp(1.1, 4.5, rhythm),
  };
}


/* ============================================================
   CSS GENERATOR
   ============================================================ */

function buildCSS(
  settings,
  edgePx
) {
  const m = metrics(settings);

  const bulletDot =
    2.5 * settings.bodyPt / 11;

  const bulletTop =
    3.8 * settings.bodyPt / 11;

  const bulletRight =
    3.7 * settings.bodyPt / 11;

  return `
:root { --page-margin: 0 !important; }

/* ============================================================
   CAREEROPS ADAPTIVE ONE-PAGE LAYOUT
   ============================================================ */

@page {
    size: Letter;
    margin: 0;
}

html,
body {
    margin: 0 !important;
    padding: 0 !important;
}


/*
  PRESERVE APPROVED VERTICAL PAGE GEOMETRY.

  edgePx is derived from the CURRENT approved top/bottom
  template padding. Left/right geometry remains untouched.
*/
.resume-page {
    width: 8.5in !important;
    height: 11in !important;

    min-height: 11in !important;
    max-height: 11in !important;

    box-sizing: border-box !important;

    padding-top:
        ${edgePx.toFixed(4)}px !important;

    padding-bottom:
        ${edgePx.toFixed(4)}px !important;

    /*
      Preserve the already-approved side geometry.
      Do not overwrite left/right padding.
    */

    overflow: visible !important;
}


/*
  Remove inherited vertical offset before the name.
*/
.resume-header,
.candidate-name {
    margin-top: 0 !important;
    padding-top: 0 !important;
}


/* ============================================================
   BODY
   ============================================================ */

body,
.resume-page,
.summary-line,
.bullet-list li,
.skill-item,
.skill-copy,
.certification-row,
.certification-copy,
.cert-item,
.edu-desc {
    font-family:
        "Calibri Resume",
        "Calibri",
        "Carlito",
        Arial,
        sans-serif !important;

    font-size:
        ${m.bodyPx.toFixed(4)}px !important;

    line-height:
        ${m.bodyLine.toFixed(4)}px !important;

    font-weight: 400;
    font-style: normal;

    letter-spacing: 0 !important;
    font-synthesis: none !important;
}


/* ============================================================
   NAME
   ============================================================ */

.candidate-name {
    font-family:
        "Times Resume",
        "Times New Roman",
        Times,
        serif !important;

    font-size:
        ${m.namePx.toFixed(4)}px !important;

    line-height:
        ${m.nameLine.toFixed(4)}px !important;

    font-weight:
        700 !important;
}


/* ============================================================
   CONTACT
   ============================================================ */

.contact-row,
.contact-row *,
.contact-row a {
    font-family:
        "Times Resume",
        "Times New Roman",
        Times,
        serif !important;

    font-size:
        ${m.contactPx.toFixed(4)}px !important;

    line-height:
        ${m.contactLine.toFixed(4)}px !important;

    font-weight:
        400 !important;
}


/*
  Contact/address -> first section is dynamic and proportional.
*/
.resume-header {
    margin-bottom:
        ${m.headerSectionGapPx.toFixed(4)}px !important;
}

.resume-header + .resume-section {
    margin-top: 0 !important;
}


/* ============================================================
   SECTION TITLES
   ============================================================ */

.section-title {
    font-family:
        "Calibri Resume",
        "Calibri",
        "Carlito",
        Arial,
        sans-serif !important;

    font-size:
        ${m.bodyPx.toFixed(4)}px !important;

    line-height:
        ${m.sectionLine.toFixed(4)}px !important;

    font-weight:
        700 !important;

    margin-top: 0 !important;

    margin-bottom:
        ${m.sectionTitleGapPt.toFixed(4)}pt !important;
}


/* ============================================================
   EXPERIENCE + PROJECT HEADERS + DATES
   ============================================================ */

.entry-header,
.entry-main,
.job-company,
.job-role,
.job-period,
.project-name,
.project-date {
    font-family:
        "Calibri Resume",
        "Calibri",
        "Carlito",
        Arial,
        sans-serif !important;

    font-size:
        ${m.entryPx.toFixed(4)}px !important;

    line-height:
        ${m.entryLine.toFixed(4)}px !important;

    font-weight:
        700 !important;

    font-style:
        normal !important;
}


/* ============================================================
   EDUCATION

   CRITICAL:
   Education dates use exactly the SAME typography
   as every other date.
   ============================================================ */

.edu-header,
.edu-header *,
.edu-title,
.edu-org,
.edu-year,
.edu-degree,
.edu-school,
.edu-date,
.education-title,
.education-degree,
.education-institution,
.education-school,
.education-date {
    font-family:
        "Calibri Resume",
        "Calibri",
        "Carlito",
        Arial,
        sans-serif !important;

    font-size:
        ${m.entryPx.toFixed(4)}px !important;

    line-height:
        ${m.entryLine.toFixed(4)}px !important;

    font-weight:
        700 !important;

    font-style:
        normal !important;
}


/*
  GPA / honors remain body typography.
*/
.edu-desc,
.education-description {
    font-size:
        ${m.bodyPx.toFixed(4)}px !important;

    line-height:
        ${m.bodyLine.toFixed(4)}px !important;

    font-weight:
        400 !important;
}


/* ============================================================
   LABELS
   ============================================================ */

.skill-category,
.cert-label {
    font-weight:
        700 !important;
}


/* ============================================================
   SECTION RHYTHM
   ============================================================ */

.resume-section + .resume-section {
    margin-top:
        ${m.majorSectionGapPt.toFixed(4)}pt !important;
}

.resume-header + .resume-section {
    margin-top: 0 !important;
}


/* ============================================================
   EXPERIENCE RHYTHM
   ============================================================ */

.job:not(:last-child) {
    margin-bottom:
        ${m.jobGapPt.toFixed(4)}pt !important;
}


/* ============================================================
   PROJECT RHYTHM
   ============================================================ */

.project:not(:last-child) {
    margin-bottom:
        ${m.projectGapPt.toFixed(4)}pt !important;
}


/* ============================================================
   BULLETS
   ============================================================ */

.bullet-list {
    margin-top: 0 !important;
    margin-bottom: 0 !important;
}

.bullet-list li:not(:last-child) {
    margin-bottom:
        ${m.bulletGapPx.toFixed(4)}px !important;
}

.bullet-list li::before {
    width:
        ${bulletDot.toFixed(4)}pt !important;

    height:
        ${bulletDot.toFixed(4)}pt !important;

    flex:
        0 0 ${bulletDot.toFixed(4)}pt !important;

    margin-top:
        ${bulletTop.toFixed(4)}pt !important;

    margin-right:
        ${bulletRight.toFixed(4)}pt !important;
}


/* ============================================================
   SKILLS
   ============================================================ */

.skill-item {
    margin-top: 0 !important;
}

.skill-item:not(:last-child) {
    margin-bottom:
        ${m.skillGapPx.toFixed(4)}px !important;
}

.skill-item:last-child {
    margin-bottom: 0 !important;
}

.certification-row {
    margin-top:
        ${m.certGapPt.toFixed(4)}pt !important;

    margin-bottom:
        0 !important;
}


/* ============================================================
   EDUCATION RHYTHM
   ============================================================ */

.education-section,
.resume-section:last-of-type {
    margin-top:
        ${m.educationGapPt.toFixed(4)}pt !important;

    margin-bottom: 0 !important;

    break-before: auto !important;
    page-break-before: auto !important;

    break-inside: auto !important;
    page-break-inside: auto !important;
}

.edu-item,
.education-item {
    break-inside: avoid !important;
    page-break-inside: avoid !important;
}
`;
}


/* ============================================================
   LOAD
   ============================================================ */

const source =
  await readFile(INPUT, 'utf8');

// Invalidate a previous fit before attempting this render; a failure must not reuse it.
await writeFile(REPORT, JSON.stringify({status:"IN_PROGRESS",content_changed:false,model_calls:0})+"\n", "utf8");

const browser =
  await chromium.launch({
    headless: true
  });

const page =
  await browser.newPage({
    viewport: {
      width: PAGE_W,
      height: PAGE_H
    }
  });

await page.emulateMedia({
  media: 'print'
});

await page.goto(
  pathToFileURL(INPUT).href,
  {
    waitUntil: 'load'
  }
);

await page.evaluate(async () => {
  if (document.fonts?.ready) {
    await document.fonts.ready;
  }
});


/* ============================================================
   AUTHORITATIVE SIDE GAP

   We use computed left/right padding from the approved
   resume template.

   That is the physical anchor for TOP and BOTTOM too.
   ============================================================ */

const sideGeometry =
  await page.evaluate(() => {
    const root =
      document.querySelector('.resume-page');

    if (!root) {
      throw new Error(
        'Missing .resume-page'
      );
    }

    const cs =
      getComputedStyle(root);

    const left =
      parseFloat(cs.paddingLeft);

    const right =
      parseFloat(cs.paddingRight);

    if (
      !Number.isFinite(left)
      || !Number.isFinite(right)
    ) {
      throw new Error(
        'Could not measure side padding'
      );
    }

    return {
      left,
      right,
      average:
        (left + right) / 2
    };
  });


/*
  CAREEROPS_VERTICAL_EDGE_PRESERVE_V2

  Left/right geometry is already locked by the template and is
  deliberately not overwritten by this adaptive layer.

  Vertical page geometry is independent. Read the template's
  actual top/bottom padding before injecting adaptive CSS and
  preserve that approved vertical edge.

  This prevents a 0.15in top/bottom design from being silently
  expanded to a 0.40in side margin.
*/
const EDGE_PX =
  await page.evaluate(() => {
    const root =
      document.querySelector(
        '.resume-page'
      );

    if (!root) {
      throw new Error(
        'Resume page missing while reading vertical geometry'
      );
    }

    const style =
      getComputedStyle(root);

    const top =
      parseFloat(
        style.paddingTop
      );

    const bottom =
      parseFloat(
        style.paddingBottom
      );

    if (
      !Number.isFinite(top)
      ||
      !Number.isFinite(bottom)
      ||
      top < 0
      ||
      bottom < 0
    ) {
      throw new Error(
        'Invalid approved vertical page geometry'
      );
    }

    return (
      top + bottom
    ) / 2;
  });


// Historical templates/careerops/cv-template.careerops.html uses 0.50in.
// Adaptive typography may fit content; it may never collapse margins.
if (EDGE_PX < 0.40 * 96 || sideGeometry.left < 0.40 * 96 || sideGeometry.right < 0.40 * 96) {
  throw new Error("RENDERER_PROFESSIONAL_MARGIN_FLOOR: minimum 0.40in on every edge");
}

/* ============================================================
   LIVE CSS
   ============================================================ */

await page.evaluate(() => {
  const style =
    document.createElement('style');

  style.id =
    'CAREEROPS_ADAPTIVE_LAYOUT_LIVE';

  document.head.appendChild(style);
});


async function apply(settings) {
  await page.evaluate(
    cssText => {
      document
        .getElementById(
          'CAREEROPS_ADAPTIVE_LAYOUT_LIVE'
        )
        .textContent = cssText;
    },
    buildCSS(
      settings,
      EDGE_PX
    )
  );

  await page.evaluate(async () => {
    if (document.fonts?.ready) {
      await document.fonts.ready;
    }

    await new Promise(resolve =>
      requestAnimationFrame(() =>
        requestAnimationFrame(resolve)
      )
    );
  });

  return measure();
}


/* ============================================================
   TRUE PHYSICAL MEASUREMENT
   ============================================================ */

async function measure() {
  return page.evaluate(
    ({
      PAGE_H,
      EDGE_PX,
      WORD_PAGINATION_RESERVE_PX
    }) => {

      const root =
        document.querySelector(
          '.resume-page'
        );

      const name =
        document.querySelector(
          '.candidate-name'
        );

      const contact =
        document.querySelector(
          '.contact-row'
        );

      const firstSection =
        document.querySelector(
          '.resume-section .section-title'
        );

      const education =
        [
          ...document.querySelectorAll(
            '.edu-item, .education-item'
          )
        ];

      if (
        !root
        || !name
        || !contact
        || !firstSection
        || !education.length
      ) {
        throw new Error(
          'Required resume nodes missing'
        );
      }

      const rr =
        root.getBoundingClientRect();

      const nr =
        name.getBoundingClientRect();

      const cr =
        contact.getBoundingClientRect();

      const sr =
        firstSection.getBoundingClientRect();

      const lastEdu =
        education[
          education.length - 1
        ].getBoundingClientRect();


      /*
        Physical page is always exactly 11in.

        We NEVER use rr.bottom as the physical page bottom.
      */
      const physicalTop =
        rr.top;

      const physicalBottom =
        rr.top + PAGE_H;

      const topGap =
        nr.top - physicalTop;

      const bottomGap =
        physicalBottom - lastEdu.bottom;

      const contactSectionGap =
        sr.top - cr.bottom;


      function lineCount(el) {
        if (!el) return 0;

        const rect =
          el.getBoundingClientRect();

        const lh =
          parseFloat(
            getComputedStyle(el).lineHeight
          );

        if (
          !Number.isFinite(lh)
          || lh <= 0
        ) {
          return 1;
        }

        return Math.max(
          1,
          Math.round(rect.height / lh)
        );
      }


      const contactLines =
        lineCount(contact);

      const summaryLines =
        lineCount(
          document.querySelector(
            '.summary-line'
          )
        );


      /*
        Header wrap checks.
      */
      const experienceHeaders =
        [
          ...document.querySelectorAll(
            '.experience-section .entry-header'
          )
        ].map(lineCount);


      /*
        Project title row.
      */
      const projectHeaders =
        [
          ...document.querySelectorAll(
            '.project-name, .project-title'
          )
        ].map(lineCount);


      /*
        Education row and date must remain aligned.
      */
      const educationHeaders =
        [
          ...document.querySelectorAll(
            '.edu-header'
          )
        ].map(lineCount);


      const wrapFailure =
        contactLines > 1

        ||

        summaryLines > 2

        ||

        experienceHeaders.some(
          x => x > 1
        )

        ||

        projectHeaders.some(
          x => x > 1
        )

        ||

        educationHeaders.some(
          x => x > 1
        );


      /*
        Content must end before the fixed bottom edge.
      */
      const physicalOverflow =
        lastEdu.bottom
        >
        physicalBottom
        - EDGE_PX - WORD_PAGINATION_RESERVE_PX
        + 0.5;


      return {
        topGap,
        bottomGap,

        topTargetError:
          Math.abs(
            topGap - EDGE_PX
          ),

        bottomTargetError:
          Math.abs(
            bottomGap - EDGE_PX - WORD_PAGINATION_RESERVE_PX
          ),

        contactSectionGap,

        contactLines,
        summaryLines,

        experienceHeaders,
        projectHeaders,
        educationHeaders,

        wrapFailure,
        physicalOverflow
      };
    },

    {
      PAGE_H,
      EDGE_PX,
      WORD_PAGINATION_RESERVE_PX
    }
  );
}


/* ============================================================
   FIT CONTACT FONT INDEPENDENTLY
   ============================================================ */

async function solveContact({
  bodyPt,
  entryPt,
  rhythm
}) {
  let lo =
    CONTACT_MIN_PT;

  let hi =
    Math.min(
      CONTACT_MAX_PT,
      bodyPt
    );

  let best =
    lo;


  for (
    let i = 0;
    i < 12;
    i++
  ) {
    const mid =
      (lo + hi) / 2;

    const m =
      await apply({
        bodyPt,
        entryPt,
        contactPt: mid,
        rhythm
      });

    if (
      m.contactLines <= 1
    ) {
      best = mid;
      lo = mid;
    } else {
      hi = mid;
    }
  }

  return best;
}


/* ============================================================
   FIT ENTRY/DATE FONT INDEPENDENTLY
   ============================================================ */

async function solveEntry({
  bodyPt,
  contactPt,
  rhythm
}) {
  let lo =
    ENTRY_MIN_PT;

  let hi =
    Math.min(
      ENTRY_MAX_PT,
      Math.max(
        ENTRY_MIN_PT,
        bodyPt * 1.08
      )
    );

  let best =
    lo;


  for (
    let i = 0;
    i < 12;
    i++
  ) {
    const mid =
      (lo + hi) / 2;

    const m =
      await apply({
        bodyPt,
        entryPt: mid,
        contactPt,
        rhythm
      });

    const headerWrap =
      m.experienceHeaders.some(
        x => x > 1
      )
      ||
      m.projectHeaders.some(
        x => x > 1
      )
      ||
      m.educationHeaders.some(
        x => x > 1
      );

    if (!headerWrap) {
      best = mid;
      lo = mid;
    } else {
      hi = mid;
    }
  }

  return best;
}


/* ============================================================
   GLOBAL SEARCH

   Enumerate body sizes because line wrapping is discontinuous.

   For each body size:
     1. solve contact font
     2. solve entry/date font
     3. solve rhythm
   ============================================================ */

const RHYTHM_MIN = 0.5;
const candidates = [];
const minimumProbes = [];


for (
  let bodyPt = BODY_MIN_PT;

  bodyPt
    <= BODY_MAX_PT + 0.0001;

  bodyPt += BODY_STEP_PT
) {

  let entryPt =
    clamp(
      bodyPt * ENTRY_RATIO,
      ENTRY_MIN_PT,
      ENTRY_MAX_PT
    );


  let contactPt =
    clamp(
      bodyPt,
      CONTACT_MIN_PT,
      CONTACT_MAX_PT
    );


  contactPt =
    await solveContact({
      bodyPt,
      entryPt,
      rhythm: RHYTHM_MIN
    });


  entryPt =
    await solveEntry({
      bodyPt,
      contactPt,
      rhythm: RHYTHM_MIN
    });


  /*
    Minimum-spacing feasibility.
  */
  const minimum =
    await apply({
      bodyPt,
      entryPt,
      contactPt,
      rhythm: RHYTHM_MIN
    });


  minimumProbes.push({bodyPt,entryPt,contactPt,measurement:minimum});
  if (
    minimum.wrapFailure
    ||
    minimum.physicalOverflow
  ) {
    continue;
  }


  /*
    Solve vertical rhythm to make the bottom edge land
    as close as possible to the side-margin target.
  */
  let low = RHYTHM_MIN;
  let high = 1;

  let bestLocal = {
    bodyPt,
    entryPt,
    contactPt,
    rhythm: RHYTHM_MIN,
    measurement: minimum
  };


  for (
    let i = 0;
    i < 20;
    i++
  ) {

    const mid =
      (low + high) / 2;


    const m =
      await apply({
        bodyPt,
        entryPt,
        contactPt,
        rhythm: mid
      });


    if (
      m.wrapFailure
      ||
      m.physicalOverflow
    ) {
      high = mid;
      continue;
    }


    if (
      m.bottomTargetError
      <
      bestLocal
        .measurement
        .bottomTargetError
    ) {
      bestLocal = {
        bodyPt,
        entryPt,
        contactPt,
        rhythm: mid,
        measurement: m
      };
    }


    /*
      Too much whitespace at bottom:
      increase rhythm.
    */
    if (
      m.bottomGap > EDGE_PX + WORD_PAGINATION_RESERVE_PX
    ) {
      low = mid;
    } else {
      high = mid;
    }
  }


  candidates.push(
    bestLocal
  );
}


/* ============================================================
   SELECT BEST LAYOUT
   ============================================================ */

if (!candidates.length) {
  await writeFile(REPORT,JSON.stringify({status:"FAIL",reason:"CONTENT_COMPRESSION_REQUIRED",minimum_probes:minimumProbes,model_calls:0},null,2));
  console.error(
    'CONTENT_COMPRESSION_REQUIRED'
  );

  console.error(
    `No professional one-page layout fits above ${BODY_MIN_PT}pt body text.`
  );

  await browser.close();
  process.exit(3);
}


/*
  Prefer layouts that physically match all four edges.

  Within that group, maximize body readability.
*/
const balanced =
  candidates.filter(
    x =>
      x.measurement
        .bottomTargetError
      <= 2.0

      &&

      x.measurement
        .topTargetError
      <= 2.0
  );


let chosen;


if (balanced.length) {
  chosen =
    balanced.sort(
      (a, b) =>
        b.bodyPt - a.bodyPt
        ||
        a.rhythm - b.rhythm
    )[0];
} else {
  /*
    If wrapping makes a perfect geometric solution
    impossible, minimize physical edge error first,
    then maximize body font.
  */
  chosen =
    candidates.sort(
      (a, b) => {
        const aError =
          a.measurement
            .topTargetError
          +
          a.measurement
            .bottomTargetError;

        const bError =
          b.measurement
            .topTargetError
          +
          b.measurement
            .bottomTargetError;

        return (
          aError - bError
          ||
          b.bodyPt - a.bodyPt
          ||
          a.rhythm - b.rhythm
        );
      }
    )[0];
}


/* ============================================================
   FINAL HARD VALIDATION
   ============================================================ */

const finalMeasurement =
  await apply(chosen);


if (
  finalMeasurement.wrapFailure
  ||
  finalMeasurement.physicalOverflow
) {
  throw new Error(
    'FINAL ADAPTIVE LAYOUT VALIDATION FAILED'
  );
}


/* ============================================================
   WRITE FITTED HTML
   ============================================================ */

const finalCSS =
  buildCSS(
    chosen,
    EDGE_PX
  );


if (!source.includes('</head>')) {
  throw new Error(
    'Input HTML has no </head>'
  );
}


const outputHTML =
  source.replace(
    '</head>',
    `
<style id="CAREEROPS_ADAPTIVE_LAYOUT_FINAL">
${finalCSS}
</style>
</head>`
  );


await writeFile(
  OUTPUT,
  outputHTML,
  'utf8'
);


/* ============================================================
   AUDIT REPORT
   ============================================================ */

const finalMetrics =
  metrics(chosen);


const report = {
  payload_sha256: process.env.CAREEROPS_RESUME_INPUT ? createHash("sha256").update(await readFile(process.env.CAREEROPS_RESUME_INPUT)).digest("hex") : null,
  status:
    'PASS',

  input:
    INPUT,

  output:
    OUTPUT,

  physical_page:
    'US Letter',

  geometry_policy: {preferred_margin_in:0.50,preferred_side_margin_in:0.65,hard_minimum_margin_in:0.40,content_selection_before_margin_collapse:true,reference:"templates/careerops/cv-template.careerops.html"},
  fixed_geometry: {
    cross_renderer_pagination_reserve_px: WORD_PAGINATION_RESERVE_PX,
    left_px:
      sideGeometry.left,

    right_px:
      sideGeometry.right,

    target_all_edges_px:
      EDGE_PX
  },

  actual_geometry: {
    top_px:
      finalMeasurement.topGap,

    bottom_px:
      finalMeasurement.bottomGap,

    top_error_px:
      finalMeasurement.topTargetError,

    bottom_error_px:
      finalMeasurement.bottomTargetError,

    contact_to_first_section_px:
      finalMeasurement.contactSectionGap
  },

  typography: {
    name_line_px: finalMetrics.nameLine,
    contact_line_px: finalMetrics.contactLine,
    entry_line_px: finalMetrics.entryLine,
    section_line_px: finalMetrics.sectionLine,
    body_pt:
      chosen.bodyPt,

    entry_and_date_pt:
      finalMetrics.entryPt,

    education_date_pt:
      finalMetrics.entryPt,

    contact_pt:
      finalMetrics.contactPt,

    name_pt:
      finalMetrics.namePt,

    body_line_px:
      finalMetrics.bodyLine
  },

  rhythm: {
    section_title_gap_pt: finalMetrics.sectionTitleGapPt,
    cert_gap_pt: finalMetrics.certGapPt,
    education_gap_pt: finalMetrics.educationGapPt,
    factor:
      chosen.rhythm,

    section_gap_pt:
      finalMetrics.majorSectionGapPt,

    job_gap_pt:
      finalMetrics.jobGapPt,

    project_gap_pt:
      finalMetrics.projectGapPt,

    bullet_gap_px:
      finalMetrics.bulletGapPx,

    skill_gap_px:
      finalMetrics.skillGapPx,

    header_to_first_section_px:
      finalMetrics.headerSectionGapPx
  },

  safety: {
    contact_lines:
      finalMeasurement.contactLines,

    summary_lines:
      finalMeasurement.summaryLines,

    experience_headers:
      finalMeasurement.experienceHeaders,

    project_headers:
      finalMeasurement.projectHeaders,

    education_headers:
      finalMeasurement.educationHeaders,

    physical_overflow:
      finalMeasurement.physicalOverflow,

    one_page_dom:
      true
  },

  content_changed:
    false,

  model_calls:
    0
};


await writeFile(
  REPORT,
  JSON.stringify(
    report,
    null,
    2
  ) + '\n',
  'utf8'
);


/* ============================================================
   CONSOLE REPORT
   ============================================================ */

console.log(
  '='.repeat(100)
);

console.log(
  'CAREEROPS ADAPTIVE ONE-PAGE LAYOUT'
);

console.log(
  '='.repeat(100)
);

console.log(
  '\nFIXED SIDE GEOMETRY'
);

console.log(
  'Left:',
  `${sideGeometry.left.toFixed(2)}px`
);

console.log(
  'Right:',
  `${sideGeometry.right.toFixed(2)}px`
);

console.log(
  'Target top/bottom:',
  `${EDGE_PX.toFixed(2)}px`
);


console.log(
  '\nACTUAL EDGES'
);

console.log(
  'Top:',
  `${finalMeasurement.topGap.toFixed(2)}px`
);

console.log(
  'Bottom:',
  `${finalMeasurement.bottomGap.toFixed(2)}px`
);


console.log(
  '\nDYNAMIC TYPOGRAPHY'
);

console.log(
  'Body:',
  `${chosen.bodyPt.toFixed(3)}pt`
);

console.log(
  'Entry + dates:',
  `${chosen.entryPt.toFixed(3)}pt`
);

console.log(
  'Education dates:',
  `${chosen.entryPt.toFixed(3)}pt`
);

console.log(
  'Contact:',
  `${chosen.contactPt.toFixed(3)}pt`
);

console.log(
  'Name:',
  `${finalMetrics.namePt.toFixed(3)}pt`
);


console.log(
  '\nDYNAMIC RHYTHM'
);

console.log(
  'Factor:',
  chosen.rhythm.toFixed(4)
);

console.log(
  'Contact -> first section:',
  `${finalMeasurement.contactSectionGap.toFixed(2)}px`
);

console.log(
  'Section gap:',
  `${finalMetrics.majorSectionGapPt.toFixed(3)}pt`
);

console.log(
  'Job gap:',
  `${finalMetrics.jobGapPt.toFixed(3)}pt`
);

console.log(
  'Project gap:',
  `${finalMetrics.projectGapPt.toFixed(3)}pt`
);

console.log(
  'Bullet gap:',
  `${finalMetrics.bulletGapPx.toFixed(3)}px`
);


console.log(
  '\nSAFETY'
);

console.log(
  'Contact:',
  `${finalMeasurement.contactLines} line`
);

console.log(
  'Summary:',
  `${finalMeasurement.summaryLines} line(s)`
);

console.log(
  'Physical overflow:',
  'NO'
);

console.log(
  'Education dates match other dates:',
  'YES'
);


console.log(
  '\nCONTENT CHANGED: NO'
);

console.log(
  'ARCHITECTURE CHANGED: NO'
);

console.log(
  'MODEL CALLS: 0'
);

console.log(
  '\nHTML:',
  OUTPUT
);

console.log(
  'REPORT:',
  REPORT
);

console.log(
  '='.repeat(100)
);


await browser.close();
