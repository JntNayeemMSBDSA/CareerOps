import { chromium } from "playwright";
import { createHash } from "node:crypto";

export const digest = value => createHash("sha256").update(value).digest("hex");

// Geometry only. Content and fixed page/design geometry are never edited.
export async function fitCoverHtml(source, binding) {
  const browser = await chromium.launch({headless: true});
  try {
    const page = await browser.newPage({viewport:{width:816,height:1056}});
    await page.emulateMedia({media:"print"});
    await page.setContent(source, {waitUntil:"load"});
    await page.evaluate(() => document.fonts.ready);
    const contentBefore = await page.locator(".cover-page").innerText();
    const margins = await page.locator('.cover-page').evaluate(e => {
      const c=getComputedStyle(e);return {top:parseFloat(c.paddingTop)/96,bottom:parseFloat(c.paddingBottom)/96,left:parseFloat(c.paddingLeft)/96,right:parseFloat(c.paddingRight)/96};
    });
    if (Object.values(margins).some(x=>x<0.40)) throw new Error('RENDERER_PROFESSIONAL_MARGIN_FLOOR');
    let chosen;
    const attempts = [];
    for (const bodyPt of [11.0,10.5]) {
      for (const rhythm of [1,0.9,0.8,0.7,0.65]) {
        for (const contactPt of [10.0]) {
          const geometry = {body_pt:bodyPt,body_line_pt:bodyPt*(1.10+0.1666666667*rhythm),
            contact_pt:contactPt,contact_line_pt:contactPt*1.06122449,rhythm,
            header_after_pt:14*rhythm,date_after_pt:8*rhythm,role_after_pt:13*rhythm,
            salutation_after_pt:10*rhythm,body_after_pt:10*rhythm,closing_before_pt:18*rhythm,
            signature_before_pt:16*rhythm,signature_after_pt:10*rhythm,signature_name_before_pt:6*rhythm};
          const css = `:root{--page-margin:0!important}
.correspondence,.letter-body{font-size:${bodyPt}pt!important;line-height:${geometry.body_line_pt}pt!important}
            .cover-header{margin-bottom:${geometry.header_after_pt}pt!important}
            .contact-row{font-size:${contactPt}pt!important;line-height:${geometry.contact_line_pt}pt!important}
            .date-line{margin-bottom:${geometry.date_after_pt}pt!important}
            .correspondence{margin-bottom:${geometry.role_after_pt}pt!important}
            .salutation{margin-bottom:${geometry.salutation_after_pt}pt!important}
            .body-paragraph{margin-bottom:${geometry.body_after_pt}pt!important}
            .closing{margin-top:${geometry.closing_before_pt}pt!important}
            .signature-image-wrap{margin-top:${geometry.signature_before_pt}pt!important;margin-bottom:${geometry.signature_after_pt}pt!important}
            .signature-name{margin-top:${geometry.signature_name_before_pt}pt!important}`;
          await page.evaluate(css => {
            let s=document.getElementById("CAREEROPS_COVER_ADAPTIVE");
            if(!s){s=document.createElement("style");s.id="CAREEROPS_COVER_ADAPTIVE";document.head.append(s);}
            s.textContent=css;
          },css);
          const measurement = await page.evaluate(() => {
            const root=document.querySelector(".cover-page"), b=root.getBoundingClientRect(), c=getComputedStyle(root);
            const left=b.left+parseFloat(c.paddingLeft),right=b.right-parseFloat(c.paddingRight),top=b.top+parseFloat(c.paddingTop),bottom=b.top+1056-parseFloat(c.paddingBottom);
            let overflow=false,contentBottom=top;const offenders=[];
            const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
            while(walker.nextNode()){
              const n=walker.currentNode;if(!n.textContent.trim())continue;
              const range=document.createRange();range.selectNodeContents(n);
              for(const rect of range.getClientRects()){
                contentBottom=Math.max(contentBottom,rect.bottom);
                if(rect.left<left-0.5||rect.right>right+0.5||rect.top<b.top-0.5||rect.bottom>bottom+0.5){overflow=true;offenders.push({class:n.parentElement.className,left:rect.left,right:rect.right,top:rect.top,bottom:rect.bottom});}
              }
            }
            for(const img of root.querySelectorAll("img")){
              const t=img.getBoundingClientRect();contentBottom=Math.max(contentBottom,t.bottom);
              if(t.left<left-0.5||t.right>right+0.5||t.bottom>bottom+0.5)overflow=true;
            }
            const lineCount=selector => {const e=root.querySelector(selector);return Math.round(e.getBoundingClientRect().height/parseFloat(getComputedStyle(e).lineHeight));};
            return {overflow,offenders,content_bottom_px:contentBottom,limit_bottom_px:bottom,contact_lines:lineCount(".contact-row"),name_lines:lineCount(".candidate-name")};
          });
          attempts.push({geometry,measurement});
          if(!measurement.overflow&&measurement.contact_lines===1&&measurement.name_lines===1){chosen={geometry,measurement,css};break;}
        }
        if(chosen)break;
      }
      if(chosen)break;
    }
    if(!chosen)throw new Error("RENDERER_LAYOUT_NO_SAFE_FIT: "+JSON.stringify({first:attempts[0],last:attempts.at(-1)}));
    if(contentBefore!==await page.locator(".cover-page").innerText())throw new Error("RENDERER_CONTENT_CHANGED");
    const html=source.replace("</head>",`<style id="CAREEROPS_COVER_ADAPTIVE">${chosen.css}</style></head>`);
    return {html,report:{schema_version:"careerops-cover-adaptive-v1",status:"PASS",binding,source_html_sha256:digest(source),fitted_html_sha256:digest(html),geometry:{...chosen.geometry,margins_in:margins},measurement:chosen.measurement,attempts:attempts.length,content_changed:false,model_calls:0}};
  } finally {await browser.close();}
}
