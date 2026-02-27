import fs from "fs";
import path from "path";
import { glob } from "glob";

// Regex to match t('key') and t("key") patterns
const TRANSLATION_KEY_REGEX = /\bt\s*\(\s*['"`]([^'"`]+)['"`]\s*\)/g;

// Recursively get all nested keys from an object
function getAllKeys(obj: Record<string, unknown>, prefix = ""): Set<string> {
  const keys = new Set<string>();
  for (const key of Object.keys(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (typeof obj[key] === "object" && obj[key] !== null) {
      getAllKeys(obj[key] as Record<string, unknown>, fullKey).forEach((k) =>
        keys.add(k),
      );
    } else {
      keys.add(fullKey);
    }
  }
  return keys;
}

// Set a nested value in an object
function setNestedValue(
  obj: Record<string, unknown>,
  key: string,
  value: string,
): void {
  const parts = key.split(".");
  let current = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (!(parts[i] in current)) {
      current[parts[i]] = {};
    }
    current = current[parts[i]] as Record<string, unknown>;
  }
  current[parts[parts.length - 1]] = value;
}

async function extractI18nKeys() {
  console.log("🔍 Scanning for translation keys...\n");

  // Find all TSX files
  const files = await glob("src/**/*.tsx", { cwd: process.cwd() });
  const extractedKeys = new Set<string>();

  // Extract keys from each file
  for (const file of files) {
    const content = fs.readFileSync(file, "utf-8");
    let match;
    while ((match = TRANSLATION_KEY_REGEX.exec(content)) !== null) {
      extractedKeys.add(match[1]);
    }
  }

  console.log(`📝 Found ${extractedKeys.size} unique translation keys\n`);

  // Load existing translations
  const localesDir = "src/i18n/locales";

  // Auto-detect locale files from the directory
  const localeFiles: Record<string, string> = {};
  if (fs.existsSync(localesDir)) {
    const files = fs.readdirSync(localesDir);
    for (const file of files) {
      if (file.endsWith(".json")) {
        const lang = path.basename(file, ".json");
        localeFiles[lang] = path.join(localesDir, file);
      }
    }
  }

  if (Object.keys(localeFiles).length === 0) {
    console.error("❌ No locale files found in", localesDir);
    process.exit(1);
  }

  console.log(
    `📚 Found locale files: ${Object.keys(localeFiles).join(", ")}\n`,
  );

  // en.json is required as the base language
  if (!("en" in localeFiles)) {
    console.error("❌ en.json is required but not found in", localesDir);
    process.exit(1);
  }

  const translations: Record<string, Record<string, unknown>> = {};
  const existingKeys: Record<string, Set<string>> = {};

  for (const [lang, filePath] of Object.entries(localeFiles)) {
    if (fs.existsSync(filePath)) {
      translations[lang] = JSON.parse(fs.readFileSync(filePath, "utf-8"));
      existingKeys[lang] = getAllKeys(translations[lang]);
    } else {
      translations[lang] = {};
      existingKeys[lang] = new Set();
    }
  }

  // Find new keys and missing keys for each language
  const newEnKeys = [...extractedKeys].filter((k) => !existingKeys.en.has(k));
  const missingKeysByLang: Record<string, string[]> = {};
  for (const lang of Object.keys(localeFiles)) {
    if (lang !== "en") {
      missingKeysByLang[lang] = [...extractedKeys].filter(
        (k) => !existingKeys[lang].has(k),
      );
    }
  }

  const totalMissing = Object.values(missingKeysByLang).reduce(
    (sum, keys) => sum + keys.length,
    0,
  );

  if (newEnKeys.length === 0 && totalMissing === 0) {
    console.log("✅ All translation keys are up to date!");
    return;
  }

  // Add new keys to en.json
  for (const key of newEnKeys) {
    setNestedValue(translations.en, key, key);
    console.log(`➕ Added to en.json: ${key}`);
  }

  // Add missing keys to other languages (marked as needing translation)
  for (const [lang, missingKeys] of Object.entries(missingKeysByLang)) {
    const placeholder = lang === "zh" ? `【待翻译】` : `[TODO]`;
    for (const key of missingKeys) {
      setNestedValue(translations[lang], key, `${placeholder}${key}`);
      console.log(`⚠️  Added to ${lang}.json (needs translation): ${key}`);
    }
  }

  // Sort keys recursively
  function sortObjectKeys(
    obj: Record<string, unknown>,
  ): Record<string, unknown> {
    const sorted: Record<string, unknown> = {};
    for (const key of Object.keys(obj).sort()) {
      if (typeof obj[key] === "object" && obj[key] !== null) {
        sorted[key] = sortObjectKeys(obj[key] as Record<string, unknown>);
      } else {
        sorted[key] = obj[key];
      }
    }
    return sorted;
  }

  // Write updated translations
  for (const [lang, filePath] of Object.entries(localeFiles)) {
    fs.writeFileSync(
      filePath,
      JSON.stringify(sortObjectKeys(translations[lang]), null, 2) + "\n",
    );
  }

  console.log(`\n✅ Updated translation files:`);
  console.log(`   - en.json: +${newEnKeys.length} keys`);
  for (const [lang, missingKeys] of Object.entries(missingKeysByLang)) {
    if (missingKeys.length > 0) {
      console.log(
        `   - ${lang}.json: +${missingKeys.length} keys (marked with ${
          lang === "zh" ? "【待翻译】" : "[TODO]"
        })`,
      );
    }
  }
}

extractI18nKeys().catch(console.error);
