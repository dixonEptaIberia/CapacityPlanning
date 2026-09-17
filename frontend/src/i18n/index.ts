import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en";
import it from "./locales/it";
import fr from "./locales/fr";
import tr from "./locales/tr";

// English is the company language (R14.1); Italian is essential (R14.2);
// French and Turkish are provided where feasible (R14.3).
export const SUPPORTED_LANGUAGES = ["en", "it", "fr", "tr"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

const STORAGE_KEY = "cpp.lang";

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    it: { translation: it },
    fr: { translation: fr },
    tr: { translation: tr },
  },
  lng: localStorage.getItem(STORAGE_KEY) ?? "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export function setLanguage(lang: SupportedLanguage) {
  localStorage.setItem(STORAGE_KEY, lang);
  void i18n.changeLanguage(lang);
}

export default i18n;
