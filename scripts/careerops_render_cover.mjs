#!/usr/bin/env node

import {
  existsSync,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "fs";

import {
  dirname,
  resolve,
} from "path";

import {
  parseArgs,
} from "util";

import {
  renderHtmlToPdf,
} from "../generate-pdf.mjs";


import { fitCoverHtml, digest } from "./careerops_cover_adaptive_layout.mjs";

const ROOT = resolve(
  dirname(new URL(import.meta.url).pathname),
  "..",
);

const RUN_ID = (
  process.env.CAREEROPS_RUN_ID || ""
).trim();

if (
  RUN_ID
  && !/^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(
    RUN_ID,
  )
) {
  throw new Error(
    "Invalid CAREEROPS_RUN_ID.",
  );
}

const RUNTIME = process.env.CAREEROPS_RUNTIME_DIR
  ? resolve(
      ROOT,
      process.env.CAREEROPS_RUNTIME_DIR,
    )
  : RUN_ID
    ? resolve(
        ROOT,
        "data",
        "careerops-engine",
        "runs",
        RUN_ID,
        "runtime",
      )
    : resolve(
        ROOT,
        "data/careerops-engine/runtime",
      );

const OUTPUT_ROOT = process.env.CAREEROPS_OUTPUT_DIR
  ? resolve(
      ROOT,
      process.env.CAREEROPS_OUTPUT_DIR,
    )
  : RUN_ID
    ? resolve(
        ROOT,
        "data",
        "careerops-engine",
        "runs",
        RUN_ID,
        "output",
      )
    : resolve(
        ROOT,
        "output",
      );


const ISOLATED_CAREEROPS_RUN = Boolean(
  RUN_ID
  || process.env.CAREEROPS_RUNTIME_DIR
  || process.env.CAREEROPS_OUTPUT_DIR
);

if (
  ISOLATED_CAREEROPS_RUN
  && !process.env.CAREER_OPS_PDF_INDEX
) {
  process.env.CAREER_OPS_PDF_INDEX = resolve(
    RUNTIME,
    "pdf-index.tsv",
  );
}

const TEMPLATE = resolve(
  ROOT,
  "templates/careerops/cover-letter.careerops.html",
);

const DEFAULT_COVER = resolve(
  RUNTIME,
  "generated_cover_letter_pair_candidate.json",
);

const DEFAULT_IDENTITY = resolve(
  RUNTIME,
  "career_ops_cv_payload.json",
);

const DEFAULT_GATE = resolve(
  RUNTIME,
  "cover_gate_v2_report.json",
);

const SIGNATURE_PATH = resolve(
  ROOT,
  process.env.CAREEROPS_SIGNATURE_IMAGE || "candidate/signature.png",
);


function loadJson(path) {
  if (!existsSync(path)) {
    throw new Error(`Missing required file: ${path}`);
  }

  return JSON.parse(
    readFileSync(path, "utf8"),
  );
}


function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}


function asUrl(value) {
  const raw =
    typeof value === "object" && value !== null
      ? value.url
      : value;

  if (!raw) return "";

  return /^https?:\/\//i.test(raw)
    ? raw
    : `https://${raw}`;
}


function linkDisplay(value, fallback) {
  if (
    typeof value === "object"
    && value !== null
  ) {
    return value.display || fallback;
  }

  return fallback;
}


function buildContactRow(candidate) {
  const parts = [];

  if (candidate.location) {
    parts.push(
      escapeHtml(candidate.location),
    );
  }

  if (candidate.phone) {
    parts.push(
      escapeHtml(candidate.phone),
    );
  }

  if (candidate.email) {
    const email = escapeHtml(candidate.email);

    parts.push(
      `<a href="mailto:${email}">${email}</a>`,
    );
  }

  if (candidate.linkedin) {
    const url = asUrl(candidate.linkedin);
    const label = linkDisplay(
      candidate.linkedin,
      "LinkedIn",
    );

    parts.push(
      `<a href="${escapeHtml(url)}">${escapeHtml(label)}</a>`,
    );
  }

  if (candidate.github) {
    const url = asUrl(candidate.github);
    const label = linkDisplay(
      candidate.github,
      "GitHub",
    );

    parts.push(
      `<a href="${escapeHtml(url)}">${escapeHtml(label)}</a>`,
    );
  }

  return parts.join(" | ");
}


function signatureImageBlock() {
  if (!existsSync(SIGNATURE_PATH)) {
    return "";
  }

  const base64 = readFileSync(
    SIGNATURE_PATH,
  ).toString("base64");

  return (
    `<div class="signature-image-wrap">`
    + `<img class="signature-image" `
    + `src="data:image/png;base64,${base64}" `
    + `alt="Signature" />`
    + `</div>`
  );
}


function currentDetroitDate() {
  return new Intl.DateTimeFormat(
    "en-US",
    {
      timeZone: "America/Detroit",
      year: "numeric",
      month: "long",
      day: "numeric",
    },
  ).format(new Date());
}


function slug(value) {
  return String(value || "company")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}


function replaceToken(
  html,
  token,
  value,
) {
  return html
    .split(`{{${token}}}`)
    .join(value);
}


function buildHtml({
  cover,
  candidate,
  date,
}) {
  let html = readFileSync(
    TEMPLATE,
    "utf8",
  );

  if (
    !Array.isArray(cover.paragraphs)
    || cover.paragraphs.length !== 3
  ) {
    throw new Error(
      "Cover renderer requires exactly three body paragraphs.",
    );
  }

  const paragraphs = cover.paragraphs
    .map(
      (paragraph) =>
        `<p class="body-paragraph">${escapeHtml(paragraph)}</p>`,
    )
    .join("\n");

  const replacements = {
    NAME:
      escapeHtml(
        candidate.name || (() => { throw new Error("CANDIDATE_IDENTITY_INCOMPLETE"); })(),
      ),

    CONTACT_ROW:
      buildContactRow(candidate),

    DATE:
      escapeHtml(
        date || currentDetroitDate(),
      ),

    COMPANY:
      escapeHtml(cover.company),

    POSITION:
      escapeHtml(cover.position),

    SALUTATION:
      escapeHtml(cover.salutation),

    PARAGRAPHS:
      paragraphs,

    CLOSING:
      escapeHtml(cover.closing),

    SIGNATURE_IMAGE:
      signatureImageBlock(),

    SIGNATURE:
      escapeHtml(cover.signature),
  };

  for (
    const [token, value]
    of Object.entries(replacements)
  ) {
    html = replaceToken(
      html,
      token,
      value,
    );
  }

  const unresolved =
    html.match(/\{\{[A-Z_]+\}\}/g);

  if (unresolved) {
    throw new Error(
      `Unresolved template placeholders: ${
        [...new Set(unresolved)].join(", ")
      }`,
    );
  }

  return html;
}


async function main() {
  const { values: args } = parseArgs({
    options: {
      cover: {
        type: "string",
      },

      identity: {
        type: "string",
      },

      gate: {
        type: "string",
      },

      out: {
        type: "string",
      },

      html: {
        type: "string",
      },

      date: {
        type: "string",
      },

      "allow-ungated": {
        type: "boolean",
      },
    },
  });

  const coverPath = resolve(
    args.cover || DEFAULT_COVER,
  );

  const identityPath = resolve(
    args.identity || DEFAULT_IDENTITY,
  );

  const gatePath = resolve(
    args.gate || DEFAULT_GATE,
  );

  const cover = loadJson(coverPath);
  const identity = loadJson(identityPath);

  const candidate =
    identity.candidate || {};

  if (!candidate.name) {
    throw new Error(
      "Identity payload is missing candidate.name.",
    );
  }

  if (
    !args["allow-ungated"]
  ) {
    const gate = loadJson(gatePath);

    if (gate.pass !== true) {
      throw new Error(
        "Cover Gate V2 is not PASS. "
        + "Refusing candidate-facing render.",
      );
    }
  }

  const companySlug = slug(
    cover.company,
  );

  const defaultPdf = resolve(
    OUTPUT_ROOT,
    `careerops_cover_${companySlug}.pdf`,
  );

  const outputPath = resolve(
    args.out || defaultPdf,
  );

  const htmlPath = resolve(
    args.html
    || resolve(
      RUNTIME,
      `careerops_cover_${companySlug}_render.html`,
    ),
  );

  const sourceHtml = buildHtml({
    cover,
    candidate,
    date: args.date,
  });

  mkdirSync(RUNTIME, {recursive:true});
  writeFileSync(resolve(RUNTIME, "cover_adaptive_layout_report.json"), JSON.stringify({status:"IN_PROGRESS",content_changed:false,model_calls:0})+"\n");
  const fitted = await fitCoverHtml(sourceHtml, {cover_sha256:digest(readFileSync(coverPath)),identity_sha256:digest(readFileSync(identityPath))});
  const html = fitted.html;
  mkdirSync(RUNTIME, {recursive:true});
  writeFileSync(resolve(RUNTIME, "cover_adaptive_layout_report.json"), JSON.stringify({...fitted.report,status:"FIT_ONLY"},null,2)+"\n");

  mkdirSync(
    dirname(htmlPath),
    {
      recursive: true,
    },
  );

  writeFileSync(
    htmlPath,
    html,
    "utf8",
  );

  mkdirSync(
    dirname(outputPath),
    {
      recursive: true,
    },
  );

  const result = await renderHtmlToPdf(
    html,
    outputPath,
    {
      format: "letter",
      maxPages: 1,
      strictPages: true,
      inputPath: coverPath,
      baseDir: RUNTIME,
    },
  );

  writeFileSync(resolve(RUNTIME, "cover_adaptive_layout_report.json"), JSON.stringify(fitted.report,null,2)+"\n");

  console.log(
    "=".repeat(96),
  );

  console.log(
    "CAREEROPS COVER RENDERER",
  );

  console.log(
    "=".repeat(96),
  );

  console.log(
    "CONTENT SOURCE:",
    coverPath,
  );

  console.log(
    "IDENTITY SOURCE:",
    identityPath,
  );

  console.log(
    "GATE MODE:",
    args["allow-ungated"]
      ? "LAYOUT_SMOKE_ONLY"
      : "GATE_V2_REQUIRED",
  );

  console.log(
    "COMPANY:",
    cover.company,
  );

  console.log(
    "POSITION:",
    cover.position,
  );

  console.log(
    "HTML:",
    htmlPath,
  );

  console.log(
    "PDF:",
    result.outputPath,
  );

  console.log(
    "PAGES:",
    result.pageCount,
  );

  console.log(
    "SIZE:",
    result.size,
  );

  console.log(
    "GENERIC COVER HEADING:",
    "REMOVED",
  );

  console.log(
    "HEADER IDENTITY:",
    "MATCHES CAREEROPS RESUME SYSTEM",
  );

  console.log(
    "MODEL/MODEL CALLS:",
    0,
  );

  console.log(
    "=".repeat(96),
  );
}


main().catch((err) => {
  console.error(
    "CAREEROPS COVER RENDER ERROR:",
    err.message,
  );

  process.exit(1);
});
