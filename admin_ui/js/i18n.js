/**
 * i18n.js — Bilingual (Arabic / English) runtime language switching.
 *
 * Features:
 * - Default language = English
 * - Saves selected language in localStorage
 * - Applies text / placeholder / title translations
 * - Sets document direction correctly (ar = rtl, en = ltr)
 * - Exposes a global I18N object
 * - Can re-apply translations after dynamic rendering
 */

const I18N = {
  supportedLangs: ['en', 'ar'],
  fallbackLang: 'en',
  storageKey: 'firduty_lang',

  translations: {},
  currentLang: 'en',

  init() {
    const saved = localStorage.getItem(this.storageKey);
    this.currentLang = this.supportedLangs.includes(saved) ? saved : this.fallbackLang;
    return this.load(this.currentLang);
  },

  async load(lang = 'en') {
    const safeLang = this.supportedLangs.includes(lang) ? lang : this.fallbackLang;
    this.currentLang = safeLang;
    localStorage.setItem(this.storageKey, safeLang);

    try {
      const res = await fetch(`i18n/${safeLang}.json?v=${Date.now()}`, {
        cache: 'no-store'
      });

      if (!res.ok) {
        throw new Error(`Failed to load i18n file: ${res.status}`);
      }

      this.translations = await res.json();
    } catch (err) {
      console.error('Failed to load translations:', err);
      this.translations = {};
    }

    this.applyDirection();
    this.applyTranslations(document);
    this.updateLanguageButtons();

    document.dispatchEvent(new CustomEvent('languageChanged', {
      detail: { lang: this.currentLang }
    }));

    return this.currentLang;
  },

  getLang() {
    return this.currentLang;
  },

  t(key, fallback = null) {
    if (!key) return '';
    return this.translations[key] ?? fallback ?? key;
  },

  applyTranslations(root = document) {
    if (!root || !root.querySelectorAll) return;

    root.querySelectorAll('[data-i18n]').forEach((el) => {
      const key = el.getAttribute('data-i18n');
      const value = this.t(key);
      el.textContent = value;
    });

    root.querySelectorAll('[data-i18n-placeholder]').forEach((el) => {
      const key = el.getAttribute('data-i18n-placeholder');
      const value = this.t(key);
      el.setAttribute('placeholder', value);
    });

    root.querySelectorAll('[data-i18n-title]').forEach((el) => {
      const key = el.getAttribute('data-i18n-title');
      const value = this.t(key);
      el.setAttribute('title', value);
    });

    root.querySelectorAll('[data-i18n-value]').forEach((el) => {
      const key = el.getAttribute('data-i18n-value');
      const value = this.t(key);
      el.value = value;
    });
  },

  applyDirection() {
    const isArabic = this.currentLang === 'ar';
    document.documentElement.lang = this.currentLang;
    document.documentElement.dir = isArabic ? 'rtl' : 'ltr';
    document.body?.setAttribute('dir', isArabic ? 'rtl' : 'ltr');
  },

  async toggle() {
    const nextLang = this.currentLang === 'en' ? 'ar' : 'en';
    await this.load(nextLang);
  },

  updateLanguageButtons() {
    const toggleEls = document.querySelectorAll('[data-lang-toggle]');
    toggleEls.forEach((el) => {
      el.textContent = this.currentLang === 'en' ? 'عربي | EN' : 'EN | عربي';
    });
  }
};

window.I18N = I18N;

document.addEventListener('DOMContentLoaded', async () => {
  await I18N.init();

  document.querySelectorAll('[data-lang-toggle]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await I18N.toggle();
    });
  });
});