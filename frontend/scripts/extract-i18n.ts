import fs from "fs";
import path from "path";
import { glob } from "glob";

// Regex to match t('key'), t("key"), and t(`key`) patterns (including template literals with ${...})
// Captures group 1 = quote delimiter, group 2 = key string
const TRANSLATION_KEY_REGEX = /\bt\s*\(\s*(['"`])([^'"`]+)\1\s*[,)]/g;

// Regex to detect dynamic key patterns containing ${...}
const DYNAMIC_KEY_REGEX = /\$\{[^}]+\}/;

// Known dynamic fallback keys used by i18next (key name is a template, value is the fallback)
const KNOWN_DYNAMIC_FALLBACK_PREFIXES = [
  "fileUpload.categories.${category}",
  "skillSelector.sources.${cat}",
  "tools.categories.${cat}",
];

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

// Check translation files for problematic entries
function checkTranslations(
  translations: Record<string, Record<string, unknown>>,
): {
  dynamicKeys: Record<string, string[]>;
  placeholderValues: Record<string, string[]>;
} {
  const dynamicKeys: Record<string, string[]> = {};
  const placeholderValues: Record<string, string[]> = {};

  for (const [lang, obj] of Object.entries(translations)) {
    const dynamic: string[] = [];
    const placeholders: string[] = [];

    function walk(current: Record<string, unknown>, prefix: string) {
      for (const key of Object.keys(current)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;
        const value = current[key];

        // Detect keys containing ${...} (skip known fallback patterns)
        if (
          DYNAMIC_KEY_REGEX.test(key) &&
          !KNOWN_DYNAMIC_FALLBACK_PREFIXES.includes(fullKey)
        ) {
          dynamic.push(fullKey);
        }

        if (typeof value === "string") {
          // Detect values that are just the key path (untranslated placeholder)
          if (value === fullKey) {
            placeholders.push(fullKey);
          }
        } else if (typeof value === "object" && value !== null) {
          walk(value as Record<string, unknown>, fullKey);
        }
      }
    }

    walk(obj, "");

    if (dynamic.length > 0) dynamicKeys[lang] = dynamic;
    if (placeholders.length > 0) placeholderValues[lang] = placeholders;
  }

  return { dynamicKeys, placeholderValues };
}

async function extractI18nKeys() {
  console.log("🔍 Scanning for translation keys...\n");

  // Find all TSX files
  const files = await glob("src/**/*.tsx", { cwd: process.cwd() });
  const extractedKeys = new Set<string>();
  const dynamicKeyPrefixes = new Set<string>();

  // Extract keys from each file
  for (const file of files) {
    const content = fs.readFileSync(file, "utf-8");
    let match;
    while ((match = TRANSLATION_KEY_REGEX.exec(content)) !== null) {
      const key = match[2];
      if (DYNAMIC_KEY_REGEX.test(key)) {
        // Extract the static prefix before ${...}, e.g. "tools.categories" from "tools.categories.${cat}"
        const prefix = key.replace(/\$\{[^}]+\}.*/, "").replace(/\.$/, "");
        if (prefix) dynamicKeyPrefixes.add(prefix);
      } else {
        extractedKeys.add(key);
      }
    }
  }

  console.log(
    `📝 Found ${extractedKeys.size} static keys and ${dynamicKeyPrefixes.size} dynamic key patterns\n`,
  );

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

  // Check for problematic entries in translation files
  const { dynamicKeys, placeholderValues } = checkTranslations(translations);
  let hasIssues = false;

  if (Object.keys(dynamicKeys).length > 0) {
    hasIssues = true;
    console.log(
      "⚠️  Dynamic keys found (contain ${...}, not viable as static translations):",
    );
    for (const [lang, keys] of Object.entries(dynamicKeys)) {
      console.log(`   ${lang}.json:`);
      for (const key of keys) {
        console.log(`     - ${key}`);
      }
    }
    console.log();
  }

  if (Object.keys(placeholderValues).length > 0) {
    hasIssues = true;
    console.log(
      "⚠️  Untranslated placeholder values found (value equals key path):",
    );
    for (const [lang, keys] of Object.entries(placeholderValues)) {
      console.log(`   ${lang}.json:`);
      for (const key of keys) {
        console.log(`     - ${key}`);
      }
    }
    console.log();
  }

  if (hasIssues) {
    console.log("ℹ️  Please fix the above issues in the translation files.\n");
  }

  // Find new keys and missing keys for each language
  // A key is "covered" if it exists in the locale OR if a dynamic prefix pattern matches it
  const isKeyCovered = (key: string, langKeys: Set<string>): boolean => {
    if (langKeys.has(key)) return true;
    for (const prefix of dynamicKeyPrefixes) {
      if (key === prefix || key.startsWith(`${prefix}.`)) return true;
    }
    return false;
  };

  const newEnKeys = [...extractedKeys].filter(
    (k) => !isKeyCovered(k, existingKeys.en),
  );
  const missingKeysByLang: Record<string, string[]> = {};
  for (const lang of Object.keys(localeFiles)) {
    if (lang !== "en") {
      missingKeysByLang[lang] = [...extractedKeys].filter(
        (k) => !isKeyCovered(k, existingKeys[lang]),
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
