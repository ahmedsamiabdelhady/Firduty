/**
 * i18n.js — Internationalization module for Firduty Admin UI
 * Supports: Arabic (ar, RTL) and English (en, LTR)
 */

const I18N = (() => {
  let currentLang = localStorage.getItem('firduty_lang') || 'ar';
  let translations = {};

  /** Load translation file for the given language */
  async function load(lang) {
    const res = await fetch(`/i18n/${lang}.json`);
    translations = await res.json();
    currentLang = lang;
    localStorage.setItem('firduty_lang', lang);
    applyDirection();
    applyTranslations();
  }

  /** Apply RTL/LTR direction to the HTML element */
  function applyDirection() {
    document.documentElement.setAttribute('dir', currentLang === 'ar' ? 'rtl' : 'ltr');
    document.documentElement.setAttribute('lang', currentLang);
  }

  /** Apply translations to all elements with data-i18n attribute */
  function applyTranslations() {
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (translations[key]) {
        el.textContent = translations[key];
      }
    });
    // Also handle placeholders
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (translations[key]) {
        el.setAttribute('placeholder', translations[key]);
      }
    });
  }

  /** Get a translated string */
  function t(key) {
    return translations[key] || key;
  }

  /** Toggle between ar and en */
  async function toggle() {
    await load(currentLang === 'ar' ? 'en' : 'ar');
  }

  /** Get current language */
  function getLang() {
    return currentLang;
  }

  return { load, t, toggle, getLang, applyTranslations };
})();