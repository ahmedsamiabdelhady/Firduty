/**
 * i18n.js — Bilingual (Arabic / English) runtime language switching.
 *
 * Usage:
 *   I18N.load('ar')          — load a language and apply translations to the DOM
 *   I18N.getLang()           — returns current language code ('ar' | 'en')
 *   I18N.t('key')            — return a translated string
 *
 * Translations are loaded from:
 *   i18n/ar.json  (Arabic)
 *   i18n/en.json  (English)
 *
 * HTML elements opt-in to translation via data attributes:
 *   data-i18n="key"             → element.textContent = I18N.t(key)
 *   data-i18n-placeholder="key" → element.placeholder  = I18N.t(key)
 *   data-i18n-title="key"       → element.title        = I18N.t(key)
 * i18n.js — Bilingual (Arabic / English) runtime language switching.
 */

const I18N = {
  translations: {},
  currentLang: 'en',

  /** Load language file and apply translations */
  async load(lang = 'ar') {
    this.currentLang = lang;
    localStorage.setItem('firduty_lang', lang);

    try {
      const res = await fetch(`i18n/${lang}.json?v=${Date.now()}`);
      this.translations = await res.json();
    } catch (err) {
      console.error('Failed to load translations:', err);
      this.translations = {};
    }

    this.applyTranslations(document);
    this.applyDirection();
  },

  /** Get current language */
  getLang() {
    return this.currentLang;
  },

  /** Translate a key */
  t(key) {
    return this.translations[key] || key;
  },

  /** Apply translations to DOM */
  applyTranslations(root = document) {

    // textContent
    root.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      const value = this.t(key);
      if (value) el.textContent = value;
    });

    // placeholder
    root.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      const value = this.t(key);
      if (value) el.placeholder = value;
    });

    // title
    root.querySelectorAll('[data-i18n-title]').forEach(el => {
      const key = el.getAttribute('data-i18n-title');
      const value = this.t(key);
      if (value) el.title = value;
    });
  },

  /** Toggle language */
  async toggle() {
    const next = this.currentLang === 'ar' ? 'en' : 'ar';
    await this.load(next);
  },

  /** Apply page direction (RTL / LTR) */
  applyDirection() {
    const dir = this.currentLang === 'ar' ? 'rtl' : 'ltr';
    document.documentElement.dir = dir;
    document.documentElement.lang = this.currentLang;
  }
};

// expose globally
window.I18N = I18N;