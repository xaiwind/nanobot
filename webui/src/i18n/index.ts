import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import {
  channelLocaleNamespaces,
  channelLocaleResources,
} from "@/channel-plugins/locale-registry";

import {
  applyDocumentLocale,
  defaultLocale,
  fallbackLocale,
  LOCALE_STORAGE_KEY,
  normalizeLocale,
  persistLocale,
  resolveInitialLocale,
  supportedLocales,
  type SupportedLocale,
} from "./config";

type LocaleResource = Record<string, unknown>;

// Each `common.json` weighs 35-56 kB. Importing all ten statically parked
// ~450 kB of translations nobody reads in the entry chunk, so every locale is
// its own chunk fetched on demand. `./resources.ts` keeps the eager copy for
// tests; importing it from app code would undo this.
const localeLoaders = import.meta.glob<{ default: LocaleResource }>(
  "./locales/*/common.json",
);

const registeredLocales = new Set<SupportedLocale>();

/** Fetch one locale bundle and hand its namespaces to i18next. */
export async function loadLocaleResources(locale: SupportedLocale): Promise<void> {
  if (registeredLocales.has(locale)) return;
  const loadLocale = localeLoaders[`./locales/${locale}/common.json`];
  if (!loadLocale) {
    throw new Error(`missing locale bundle for ${locale}`);
  }
  const { default: common } = await loadLocale();
  i18n.addResourceBundle(locale, "common", common, true, true);
  for (const [namespace, resource] of Object.entries(channelLocaleResources(locale))) {
    i18n.addResourceBundle(locale, namespace, resource, true, true);
  }
  registeredLocales.add(locale);
}

const initialLocale = resolveInitialLocale();

const initialized: Promise<unknown> = i18n.isInitialized
  ? Promise.resolve()
  : i18n
      .use(initReactI18next)
      .init({
        resources: {},
        lng: initialLocale,
        fallbackLng: fallbackLocale,
        defaultNS: "common",
        ns: ["common", ...channelLocaleNamespaces()],
        interpolation: {
          escapeValue: false,
        },
        returnNull: false,
        supportedLngs: supportedLocales.map((locale) => locale.code),
      });

/**
 * Resolves once the active locale — plus the English fallback it defers to —
 * are in memory. `main.tsx` waits on this so the first paint never flashes
 * raw translation keys.
 */
export const i18nReady: Promise<void> = initialized.then(async () => {
  await loadLocaleResources(initialLocale);
  if (initialLocale !== fallbackLocale) {
    await loadLocaleResources(fallbackLocale);
  }
});

export function currentLocale(): SupportedLocale {
  return normalizeLocale(i18n.resolvedLanguage ?? i18n.language ?? defaultLocale);
}

export async function setAppLanguage(locale: SupportedLocale): Promise<void> {
  await loadLocaleResources(locale);
  await i18n.changeLanguage(locale);
}

const syncLocaleSideEffects = (language: string) => {
  const locale = normalizeLocale(language);
  applyDocumentLocale(locale);
  persistLocale(locale);
};

syncLocaleSideEffects(currentLocale());
i18n.on("languageChanged", syncLocaleSideEffects);

export { LOCALE_STORAGE_KEY };
export default i18n;
