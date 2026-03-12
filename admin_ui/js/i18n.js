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
 */

const I18N = (() => {
  let _strings = {};
  let _lang = 'ar';

  /**
   * Load a language pack and apply translations to the page.
   * Persists the selection to localStorage as 'firduty_lang'.
   * @param {string} lang — 'ar' or 'en'
   */
  async function load(lang) {
    _lang = (lang === 'en') ? 'en' : 'ar';
    localStorage.setItem('firduty_lang', _lang);

    try {
      const res = await fetch(`i18n/${_lang}.json?v=${Date.now()}`);
      if (!res.ok) throw new Error(`Failed to load i18n/${_lang}.json`);
      _strings = await res.json();
    } catch (err) {
      console.warn('[i18n] Could not load language pack:', err);
      _strings = {};
    }

    _apply();
  }

  /**
   * Return the current language code.
   * @returns {'ar'|'en'}
   */
  function getLang() {
    return _lang;
  }

  /**
   * Translate a key. Returns the key itself if not found.
   * @param {string} key
   * @returns {string}
   */
  function t(key) {
    return _strings[key] || key;
  }

  /**
   * Apply translations to the entire document.
   * Also sets <html lang> and <html dir> for correct RTL/LTR rendering.
   */
  function _apply() {
    // Set document direction and language
    document.documentElement.lang = _lang;
    document.documentElement.dir  = (_lang === 'ar') ? 'rtl' : 'ltr';

    // Translate text content
    document.querySelectorAll('[data-i18n]').forEach(el => {
      const key = el.getAttribute('data-i18n');
      if (key) el.textContent = t(key);
    });

    // Translate placeholder attributes
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
      const key = el.getAttribute('data-i18n-placeholder');
      if (key) el.placeholder = t(key);
    });

    // Translate title attributes (tooltips)
    document.querySelectorAll('[data-i18n-title]').forEach(el => {
      const key = el.getAttribute('data-i18n-title');
      if (key) el.title = t(key);
    });
  }

  return { load, getLang, t };
})();