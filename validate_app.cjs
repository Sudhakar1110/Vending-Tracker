#!/usr/bin/env node
/* eslint-disable no-console */
/**
 * Static validation for the vending_tracker Frappe app.
 *
 * Usage: node validate_app.py   (or: python validate_app.py is NOT required —
 * this file is intentionally plain JS so it runs anywhere Node is available)
 *
 * Checks:
 *  1. Every .json file parses.
 *  2. Python files have balanced brackets/quotes (best-effort syntax guard).
 *  3. Every fixture listed in hooks.py has a matching fixture file.
 *  4. Every fixture file's records declare a valid doctype.
 *  5. Doctype JSONs carry required keys (module, fields, permissions).
 *  6. Report folders are complete (py, js, json, __init__.py).
 *  7. Workspace content references resolve to shipped charts/cards/shortcuts.
 *  8. hooks.py doc_events reference existing dotted paths.
 */
const fs = require("fs");
const path = require("path");

const ROOT = __dirname;
const APP = path.join(ROOT, "vending_tracker");
let errors = [];
let warnings = [];

function walk(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else out.push(full);
  }
  return out;
}

function rel(p) {
  return path.relative(ROOT, p).split(path.sep).join("/");
}

function check(cond, msg) {
  if (!cond) errors.push(msg);
}

// ---------------------------------------------------------------------------
// 1. JSON parse check
// ---------------------------------------------------------------------------
const jsonFiles = walk(ROOT).filter((f) => f.endsWith(".json"));
const parsed = {};
for (const file of jsonFiles) {
  try {
    parsed[rel(file)] = JSON.parse(fs.readFileSync(file, "utf8"));
  } catch (e) {
    errors.push(`Invalid JSON in ${rel(file)}: ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// 2. Python bracket/quote balance (best effort)
// ---------------------------------------------------------------------------
function pyBalance(content) {
  const pairs = { "(": ")", "[": "]", "{": "}" };
  const closing = { ")": "(", "]": "[", "}": "{" };
  const stack = [];
  let i = 0;
  let inString = null;
  let inComment = false;
  while (i < content.length) {
    const c = content[i];
    const n = content[i + 1];
    const line = content.slice(0, i).split("\n").length;
    if (inComment) {
      if (c === "\n") inComment = false;
      i++;
      continue;
    }
    if (inString) {
      if (c === "\\") { i += 2; continue; }
      if (inString === "'''" || inString === '"""') {
        // triple-quoted: only close when we see the full closing triple
        if (c === inString[0] && content[i + 1] === inString[0] && content[i + 2] === inString[0]) {
          inString = null;
          i += 3;
        } else {
          i++;
        }
        continue;
      }
      if (c === inString) inString = null;
      else if (c === "\n") inString = null; // single-quoted strings cannot span lines
      i++;
      continue;
    }
    if (c === "#") { inComment = true; i++; continue; }
    if (c === "'" || c === '"') {
      inString = c === "'" && n === "'" && content[i + 2] === "'" ? "'''"
        : c === '"' && n === '"' && content[i + 2] === '"' ? '"""'
        : c;
      i += inString.length;
      continue;
    }
    if (pairs[c]) { stack.push(pairs[c]); i++; continue; }
    if (closing[c]) {
      const actual = stack.pop();
      if (actual !== c) {
        return `line ${line}: mismatched '${c}' (stack top was '${actual || "nothing"}')`;
      }
      i++;
      continue;
    }
    i++;
  }
  if (stack.length) return `unclosed at end of file: ${stack.join(", ")}`;
  return null;
}

const pyFiles = walk(ROOT).filter((f) => f.endsWith(".py"));
for (const file of pyFiles) {
  const content = fs.readFileSync(file, "utf8");
  const issue = pyBalance(content);
  if (issue) errors.push(`Possible Python syntax issue in ${rel(file)}: ${issue}`);
}

// ---------------------------------------------------------------------------
// 3. hooks.py fixtures <-> fixture files
// ---------------------------------------------------------------------------
const hooksContent = fs.readFileSync(path.join(APP, "hooks.py"), "utf8");
const fixturesMatch = hooksContent.match(/fixtures\s*=\s*\[([\s\S]*?)\]/);
const fixtureDoctypes = [];
if (fixturesMatch) {
  const re = /"([^"]+)"/g;
  let m;
  while ((m = re.exec(fixturesMatch[1]))) fixtureDoctypes.push(m[1]);
}
const fixtureDir = path.join(APP, "fixtures");
for (const dt of fixtureDoctypes) {
  const scrub = dt.toLowerCase().replace(/\s+/g, "_");
  const file = path.join(fixtureDir, `${scrub}.json`);
  if (!fs.existsSync(file)) {
    errors.push(`Fixture '${dt}' listed in hooks.py but no fixtures/${scrub}.json found`);
  } else {
    const data = parsed[rel(file)];
    if (data) {
      for (const rec of Array.isArray(data) ? data : [data]) {
        check(rec && rec.doctype === dt, `fixtures/${scrub}.json contains a record whose doctype is not '${dt}'`);
        if (rec && rec.doctype === "Property Setter") {
          check(
            !!rec.doctype_or_field,
            `fixtures/${scrub}.json: Property Setter '${rec.name}' is missing 'doctype_or_field' (Applied On)`
          );
          check(
            !!rec.doc_type && !!rec.property && !!rec.property_type,
            `fixtures/${scrub}.json: Property Setter '${rec.name}' is missing doc_type/property/property_type`
          );
        }
        if (rec && rec.doctype === "Server Script") {
          // frappe v15 validates Code fields with compile_command(..., "exec"),
          // which rejects a top-level `return` ('return' outside function).
          const scriptLines = (rec.script || "").split(/\n/);
          const hasTopLevelReturn = scriptLines.some(
            (l) => /^return\s/.test(l) || l.trim() === "return"
          );
          check(
            !hasTopLevelReturn,
            `fixtures/${scrub}.json: Server Script '${rec.name}' uses a top-level return; use frappe.response['message'] instead`
          );
        }
      }
    }
  }
}

// ---------------------------------------------------------------------------
// 4. Doctype JSON sanity
// ---------------------------------------------------------------------------
function scrub(name) {
  return name.toLowerCase().replace(/\s+/g, "_");
}

const doctypeFiles = walk(path.join(APP, "vending_tracker", "doctype")).filter((f) => f.endsWith(".json") && !f.endsWith("_test.json"));
for (const file of doctypeFiles) {
  const doc = parsed[rel(file)];
  if (!doc) continue;
  const name = path.basename(file, ".json");
  check(scrub(doc.name) === name, `${rel(file)}: doctype 'name' does not match filename (${doc.name} != ${name})`);
  check(!!doc.module, `${rel(file)}: missing 'module'`);
  check(Array.isArray(doc.fields) && doc.fields.length, `${rel(file)}: missing 'fields'`);
  check(Array.isArray(doc.permissions) && doc.permissions.length, `${rel(file)}: missing 'permissions'`);
  const fieldnames = new Set(doc.fields.map((f) => f.fieldname));
  for (const f of doc.fields) {
    if (f.fieldtype === "Table" && !/^[A-Za-z]/.test(f.options || "")) {
      errors.push(`${rel(file)}: Table field '${f.fieldname}' has no options`);
    }
    if (f.fieldname && fieldnames.has(f.fieldname)) {
      // duplicate fieldnames
    }
  }
  const dupes = doc.fields.map((f) => f.fieldname).filter((fn, i, a) => a.indexOf(fn) !== i);
  check(dupes.length === 0, `${rel(file)}: duplicate fieldname(s): ${dupes.join(", ")}`);
  // naming_rule pairing sanity
  if (doc.autoname && doc.autoname.startsWith("field:")) {
    check(doc.naming_rule === "By fieldname", `${rel(file)}: field-based autoname should pair with naming_rule 'By fieldname'`);
  }
}

// ---------------------------------------------------------------------------
// 5. Report folder completeness
// ---------------------------------------------------------------------------
const reportDirs = walk(path.join(APP, "vending_tracker", "report")).filter((f) => f.endsWith(".json"));
for (const file of reportDirs) {
  const dir = path.dirname(file);
  const name = path.basename(file, ".json");
  for (const suffix of [".py", ".js"]) {
    check(fs.existsSync(path.join(dir, name + suffix)), `${rel(dir)}: missing ${name + suffix}`);
  }
  check(fs.existsSync(path.join(dir, "__init__.py")), `${rel(dir)}: missing __init__.py`);
  const doc = parsed[rel(file)];
  if (doc) {
    check(doc.report_type === "Script Report" || doc.report_type === "Query Report",
      `${rel(file)}: invalid report_type '${doc.report_type}'`);
    if (doc.report_type === "Query Report") {
      // 'filters' is a child-table field (Report Filter rows): it must be an
      // array, NOT a JSON-encoded string. A string breaks DocType sync with
      // "'str' object does not support item assignment" during install.
      check(
        Array.isArray(doc.filters) && doc.filters.length,
        `${rel(file)}: query report should define 'filters' as an array of Report Filter rows`
      );
      for (const f of Array.isArray(doc.filters) ? doc.filters : []) {
        check(
          f && typeof f === "object" && f.fieldname,
          `${rel(file)}: each 'filters' row must be an object with a 'fieldname'`
        );
      }
    }
  }
}

// ---------------------------------------------------------------------------
// 6. Workspace content references
// ---------------------------------------------------------------------------
const workspaceFiles = walk(path.join(APP, "vending_tracker", "workspace")).filter((f) => f.endsWith(".json"));
const numberCardNames = new Set();
const chartNames = new Set();
const shortcutNames = new Set();
for (const f of walk(path.join(APP, "vending_tracker", "number_card")).filter((x) => x.endsWith(".json"))) {
  numberCardNames.add(parsed[rel(f)] ? parsed[rel(f)].label : null);
}
for (const f of walk(path.join(APP, "vending_tracker", "dashboard_chart")).filter((x) => x.endsWith(".json"))) {
  chartNames.add(parsed[rel(f)] ? parsed[rel(f)].chart_name : null);
}
for (const f of walk(path.join(APP, "vending_tracker", "workspace")).filter((x) => x.endsWith(".json"))) {
  const doc = parsed[rel(f)];
  if (doc && Array.isArray(doc.shortcuts)) {
    for (const s of doc.shortcuts) shortcutNames.add(s.shortcut_name);
  }
}
for (const file of workspaceFiles) {
  const doc = parsed[rel(file)];
  if (!doc) continue;
  try {
    const content = JSON.parse(doc.content);
    for (const item of content) {
      const d = item.data || {};
      if (item.type === "number_card") {
        check(numberCardNames.has(d.number_card_name), `${rel(file)}: number card '${d.number_card_name}' not shipped`);
      }
      if (item.type === "chart") {
        check(chartNames.has(d.chart_name), `${rel(file)}: chart '${d.chart_name}' not shipped`);
      }
      if (item.type === "shortcut") {
        check(shortcutNames.has(d.shortcut_name), `${rel(file)}: shortcut '${d.shortcut_name}' missing from shortcuts table`);
      }
      if (item.type === "card") {
        const labels = (doc.links || []).filter((l) => l.type === "Card Break").map((l) => l.label);
        check(labels.includes(d.card_name), `${rel(file)}: card '${d.card_name}' missing Card Break link`);
      }
    }
  } catch (e) {
    errors.push(`${rel(file)}: workspace 'content' is not valid JSON: ${e.message}`);
  }
}

// ---------------------------------------------------------------------------
// 7. hooks doc_events reference existing functions
// ---------------------------------------------------------------------------
const docEventsRe = /doc_events\s*=\s*\{([\s\S]*?)\n\}/;
const deMatch = hooksContent.match(docEventsRe);
if (deMatch) {
  const fnRe = /"vending_tracker\.[^"]+"/g;
  let m;
  while ((m = fnRe.exec(deMatch[1]))) {
    const dotted = m[0].slice(1, -1);
    const parts = dotted.split(".");
    // drop the leading app name (we are already inside the app folder)
    const filePath = path.join(APP, ...parts.slice(1, -1)) + ".py";
    const fnName = parts[parts.length - 1];
    if (!fs.existsSync(filePath)) {
      errors.push(`doc_event ${dotted}: module file not found`);
    } else {
      const src = fs.readFileSync(filePath, "utf8");
      const re = new RegExp(`\\bdef\\s+${fnName}\\s*\\(`);
      check(re.test(src), `doc_event ${dotted}: function not defined in ${rel(filePath)}`);
    }
  }
}

// ---------------------------------------------------------------------------
// 8. modules.txt <-> module folder
// ---------------------------------------------------------------------------
const modulesTxt = fs.readFileSync(path.join(APP, "modules.txt"), "utf8").trim();
for (const mod of modulesTxt.split(/\n+/).map((s) => s.trim()).filter(Boolean)) {
  const scrub = mod.toLowerCase().replace(/\s+/g, "_");
  check(fs.existsSync(path.join(APP, scrub)), `modules.txt module '${mod}' has no folder '${scrub}'`);
}

// ---------------------------------------------------------------------------
// Report
// ---------------------------------------------------------------------------
if (errors.length) {
  console.error(`\n❌ ${errors.length} error(s):`);
  for (const e of errors) console.error(`   - ${e}`);
  process.exit(1);
}
console.log(`\n✅ Validation passed. ${jsonFiles.length} JSON files, ${pyFiles.length} Python files checked.`);
if (warnings.length) {
  console.warn(`\n⚠ ${warnings.length} warning(s):`);
  for (const w of warnings) console.warn(`   - ${w}`);
}
