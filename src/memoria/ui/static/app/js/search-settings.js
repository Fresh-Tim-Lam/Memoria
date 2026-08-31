/**

 * 检索内核设置：语义搜索、正文定位

 */

(function (global) {

  "use strict";



  const STORAGE_KEY = "-search-settings";



  const DEFAULTS = {

    embeddingEnabled: false,

    searchModes: "lexical",

    bodyLocateEnabled: false,

  };



  let diskPrefs = null;

  let onChangeHandler = null;



  function api() {

    return global.MemoriaBridge && global.MemoriaBridge.api();

  }



  function readLocal() {

    try {

      const raw = localStorage.getItem(STORAGE_KEY);

      if (!raw) return {};

      const parsed = JSON.parse(raw);

      return parsed && typeof parsed === "object" ? parsed : {};

    } catch (_) {

      return {};

    }

  }



  function writeLocal(data) {

    try {

      localStorage.setItem(STORAGE_KEY, JSON.stringify(data));

    } catch (_) {

      /* ignore */

    }

  }



  function syncDiskPrefs(data) {

    diskPrefs = {

      embeddingEnabled: !!data.embeddingEnabled,

      searchModes: data.embeddingEnabled ? "both" : "lexical",

      bodyLocateEnabled: !!data.bodyLocateEnabled,

    };

  }



  function load() {

    const merged = { ...DEFAULTS, ...(diskPrefs || {}), ...readLocal() };

    merged.embeddingEnabled = !!merged.embeddingEnabled;

    merged.searchModes = merged.embeddingEnabled ? "both" : "lexical";

    merged.bodyLocateEnabled = !!merged.bodyLocateEnabled;

    return merged;

  }



  function save(partial) {

    const next = { ...load(), ...partial };

    next.embeddingEnabled = !!next.embeddingEnabled;

    next.searchModes = next.embeddingEnabled ? "both" : "lexical";

    next.bodyLocateEnabled = !!next.bodyLocateEnabled;

    syncDiskPrefs(next);

    writeLocal(next);

    persistToDisk(next);

    onChangeHandler?.(next);

    return next;

  }



  function reset() {

    writeLocal({});

    diskPrefs = null;

    persistToDisk(DEFAULTS);

    onChangeHandler?.(load());

  }



  function persistToDisk(data) {

    const a = api();

    if (!a?.save_ui_settings) return;

    syncDiskPrefs(data);

    a.save_ui_settings({

      search: {

        embedding_enabled: !!data.embeddingEnabled,

        search_modes: data.searchModes,

        body_locate_enabled: !!data.bodyLocateEnabled,

      },

    }).catch(() => {});

  }



  function flushPendingDiskSave() {

    persistToDisk(load());

  }



  async function hydrateFromDisk() {

    const a = api();

    if (!a?.get_ui_settings) return;

    try {

      const res = await a.get_ui_settings();

      const search = res?.settings?.search;

      if (search && typeof search === "object") {

        diskPrefs = {

          embeddingEnabled: !!search.embedding_enabled,

          searchModes: search.embedding_enabled ? "both" : "lexical",

          bodyLocateEnabled: !!search.body_locate_enabled,

        };

        writeLocal({ ...readLocal(), ...diskPrefs });

      }

    } catch (_) {

      /* ignore */

    }

  }



  function onChange(fn) {

    onChangeHandler = fn;

  }



  function getSearchModes() {

    return load().searchModes || "lexical";

  }



  function isBodyLocateEnabled() {

    return !!load().bodyLocateEnabled;

  }



  function renderSettingsBody() {

    const s = load();

    return `<div class="-settings-layout -settings-layout--solo">

      <div class="-settings-form">

        <section class="-settings-section">

          <h3 class="-settings-heading">检索内核</h3>

          <p class="-muted -settings-note">Lexical 层（倒排 + jieba）始终开启。语义搜索使用<strong>本地</strong> sentence-transformers 模型（默认缓存于 <code>~/.cache/huggingface</code>）；首次下载后离线运行。向量索引持久化在知识库 <code>.memoria/cache/embeddings/</code>，仅对变更 KP 增量编码。</p>

          <label class="-settings-field -settings-field--inline">

            <input type="checkbox" data-search-setting="embeddingEnabled"${s.embeddingEnabled ? " checked" : ""}>

            <span>启用语义搜索（Embedding）</span>

          </label>

          <p class="-muted -settings-note">开启后工具栏搜索使用 Lexical + 语义双路合并；关闭则仅字面匹配。</p>

          <label class="-settings-field -settings-field--inline">

            <input type="checkbox" data-search-setting="bodyLocateEnabled"${s.bodyLocateEnabled ? " checked" : ""}>

            <span>搜索正文定位内容</span>

          </label>

          <p class="-muted -settings-note">KP 结果之外，在 md 正文行内 substring 匹配并定位（非 KP 命中，分级展示）。</p>

        </section>

      </div>

    </div>`;

  }



  function bindSettingsForm(root) {

    root.querySelectorAll("[data-search-setting]").forEach((el) => {

      const key = el.dataset.searchSetting;

      el.addEventListener("change", () => {

        if (el.type === "checkbox") {

          save({ [key]: el.checked });

        }

      });

    });

  }



  global.MemoriaSearchSettings = {

    DEFAULTS,

    load,

    save,

    reset,

    hydrateFromDisk,

    flushPendingDiskSave,

    onChange,

    getSearchModes,

    isBodyLocateEnabled,

    renderSettingsBody,

    bindSettingsForm,

  };

})(typeof window !== "undefined" ? window : globalThis);

