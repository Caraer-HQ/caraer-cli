// Font loading matches caraer-web/src/lib/fonts.ts.
const GOOGLE_FONT_PRESETS = {
  Roboto: { weights: "100;200;300;400;500;600;700;800;900", italic: true },
  Lato: { weights: "100;300;400;700;900", italic: true },
  Montserrat: { weights: "100;200;300;400;500;600;700;800;900", italic: true },
  "Open Sans": { weights: "300;400;500;600;700;800", italic: true },
  Poppins: { weights: "100;200;300;400;500;600;700;800;900", italic: true },
  Oswald: { weights: "200;300;400;500;600;700" },
  Raleway: { weights: "100;200;300;400;500;600;700;800;900", italic: true },
  Merriweather: { weights: "300;400;700;900", italic: true },
  Ubuntu: { weights: "300;400;500;700", italic: true },
  "Playfair Display": { weights: "400;500;600;700;800;900", italic: true }
};
function googleFontsStylesheet(settings) {
  const normalize = (family) => family.trim().replace(/^['"]|['"]$/g, "").trim().toLowerCase();
  const uploaded = new Set(
    collectFaces(settings?.customFonts, (url) => url).map((face) => normalize(face.family))
  );
  const selected = /* @__PURE__ */ new Set();
  for (const style of Object.values(settings?.mainStyling ?? {})) {
    for (const [key, value] of Object.entries(style ?? {})) {
      if (!key.endsWith("FontFamily") && key !== "fontFamily") continue;
      if (typeof value !== "string") continue;
      const family = Object.keys(GOOGLE_FONT_PRESETS).find((name) => normalize(name) === normalize(value));
      if (family && !uploaded.has(normalize(family))) selected.add(family);
    }
  }
  const families = [...selected].sort().map((family) => {
    const { weights, italic } = GOOGLE_FONT_PRESETS[family];
    const styles = italic ? `ital,wght@${[0, 1].flatMap((axis) => weights.split(";").map((weight) => `${axis},${weight}`)).join(";")}` : `wght@${weights}`;
    return `family=${encodeURIComponent(family)}:${styles}`;
  });
  return families.length ? `https://fonts.googleapis.com/css2?${families.join("&")}&display=swap` : null;
}
const FONT_CACHE_CONTROL = "public, max-age=31536000, s-maxage=31536000, immutable";
const FONT_MIME = {
  woff2: "font/woff2",
  woff: "font/woff",
  ttf: "font/ttf",
  otf: "font/otf"
};
function formatFromUrl(url) {
  const match = url.match(/\.([a-z0-9]+)(?:\?|$)/i);
  const ext = match?.[1]?.toLowerCase() ?? "woff2";
  if (ext === "ttf") return "truetype";
  if (ext === "otf") return "opentype";
  return ext;
}
function cssString(value) {
  return value.replace(/["\\\r\n<>]/g, "");
}
function sameOriginFontUrl(resolved) {
  if (resolved.startsWith("/")) return resolved;
  try {
    const parsed = new URL(resolved);
    const spaces = /(^|\.)digitaloceanspaces\.com$/i.test(parsed.hostname);
    if (parsed.protocol === "https:" && spaces && !parsed.username && !parsed.password) {
      return `/caraer/asset?src=${encodeURIComponent(parsed.toString())}`;
    }
  } catch {
    return resolved;
  }
  return resolved;
}
function asFonts(value) {
  if (!Array.isArray(value)) return [];
  return value.filter((item) => !!item && typeof item === "object");
}
function fontMimeType(url) {
  if (!url) return null;
  let decoded = url;
  try {
    decoded = decodeURIComponent(url);
  } catch {
    decoded = url;
  }
  const match = decoded.match(/\.(woff2|woff|ttf|otf)(?:$|[?#&])/i);
  return match ? FONT_MIME[match[1].toLowerCase()] ?? null : null;
}
function collectFaces(customFonts, assetUrl) {
  const faces = [];
  for (const font of asFonts(customFonts)) {
    const family = cssString(String(font.familyName ?? "").trim());
    if (!family) continue;
    const variants = (font.variants ?? []).filter((variant) => variant?.url);
    const hasVariable = variants.some((variant) => variant.style === "variable");
    for (const variant of variants) {
      const variable = variant.style === "variable";
      const style = variable ? "normal" : variant.style ?? "normal";
      if (hasVariable && !variable && style !== "italic") continue;
      const resolved = assetUrl(String(variant.url));
      const url = cssString(sameOriginFontUrl(resolved ?? ""));
      if (!url) continue;
      faces.push({
        family,
        url,
        format: formatFromUrl(String(variant.url)),
        weight: variable ? "100 900" : String(variant.weight ?? 400),
        style: style === "italic" ? "italic" : "normal",
        variable
      });
    }
  }
  return faces;
}
function customFontFaceCss(customFonts, assetUrl = (value) => value) {
  return collectFaces(customFonts, assetUrl).map(
    (face) => `@font-face {
  font-family: "${face.family}";
  src: url("${face.url}") format("${face.format}");
  font-weight: ${face.weight};
  font-style: ${face.style};
  font-display: block;
}`
  ).join("\n");
}
function customFontPreloads(customFonts, assetUrl = (value) => value) {
  const preloads = [];
  for (const face of collectFaces(customFonts, assetUrl)) {
    const type = fontMimeType(face.url);
    if (!type) continue;
    preloads.push({ href: face.url, type });
  }
  return preloads;
}
export {
  FONT_CACHE_CONTROL,
  customFontFaceCss,
  customFontPreloads,
  fontMimeType,
  googleFontsStylesheet
};
