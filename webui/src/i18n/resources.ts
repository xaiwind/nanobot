import { channelLocaleResources } from "@/channel-plugins/locale-registry";

import enCommon from "./locales/en/common.json";
import zhCNCommon from "./locales/zh-CN/common.json";
import zhTWCommon from "./locales/zh-TW/common.json";
import frCommon from "./locales/fr/common.json";
import jaCommon from "./locales/ja/common.json";
import koCommon from "./locales/ko/common.json";
import esCommon from "./locales/es/common.json";
import ptBRCommon from "./locales/pt-BR/common.json";
import viCommon from "./locales/vi/common.json";
import idCommon from "./locales/id/common.json";

/**
 * Every locale bundle, eagerly imported.
 *
 * App code must NOT import this module: pulling it into the runtime graph
 * would undo the lazy locale chunks in `./index.ts` and put ~450 kB of unused
 * translations back into the entry bundle. It exists for tests and tooling
 * that need to compare all locales against each other.
 */
export const resources = {
  en: { common: enCommon, ...channelLocaleResources("en") },
  "zh-CN": { common: zhCNCommon, ...channelLocaleResources("zh-CN") },
  "zh-TW": { common: zhTWCommon, ...channelLocaleResources("zh-TW") },
  fr: { common: frCommon, ...channelLocaleResources("fr") },
  ja: { common: jaCommon, ...channelLocaleResources("ja") },
  ko: { common: koCommon, ...channelLocaleResources("ko") },
  es: { common: esCommon, ...channelLocaleResources("es") },
  "pt-BR": { common: ptBRCommon, ...channelLocaleResources("pt-BR") },
  vi: { common: viCommon, ...channelLocaleResources("vi") },
  id: { common: idCommon, ...channelLocaleResources("id") },
} as const;
