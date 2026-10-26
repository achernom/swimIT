/*
 * Implementación mínima del objeto `dash` que usa dashboard/index.html,
 * para correr el tablero fuera de Claude (standalone.html).
 * API cubierta: data, onData, calc, params, setParams, resetParams, colors, setLink, refresh.
 */
(function () {
  const DATASETS = {
    resultados: '../data/processed/resultados.json',
    competencias: '../data/processed/competencias.json',
  };
  const DEFAULT_PARAMS = { meet: 'SM23', prueba: '50 Libre', sexo: 'all', comparar: 'sexo', nadador: null, nadador2: null };

  const store = {};   // id -> {status, data, message}
  const calcs = {};   // id -> {inputs, fn, cache, key}
  const listeners = [];
  let params = { ...DEFAULT_PARAMS };
  let scheduled = false;

  function notify() {
    if (scheduled) return;
    scheduled = true;
    requestAnimationFrame(() => {
      scheduled = false;
      listeners.forEach((fn) => { try { fn(); } catch (e) { console.error(e); } });
    });
  }

  function load(id) {
    if (store[id]) return;
    store[id] = { status: 'loading', data: [] };
    fetch(DATASETS[id])
      .then((r) => { if (!r.ok) throw new Error(r.status + ' ' + r.statusText); return r.json(); })
      .then((json) => { store[id] = { status: 'ok', data: json, columns: json.length ? Object.keys(json[0]) : [] }; notify(); })
      .catch((e) => { store[id] = { status: 'error', data: [], message: String(e) }; notify(); });
  }

  function data(id) {
    if (calcs[id]) {
      const c = calcs[id];
      const ins = c.inputs.map((i) => data(i));
      const bad = ins.find((d) => d.status !== 'ok');
      if (bad) return { status: bad.status, data: [], message: bad.message };
      const key = ins.map((d) => d.data);
      if (!c.key || c.key.some((k, i) => k !== key[i])) {
        try { c.cache = { status: 'ok', data: c.fn(...key) }; } catch (e) { c.cache = { status: 'error', data: [], message: String(e) }; }
        c.key = key;
      }
      return c.cache;
    }
    if (!DATASETS[id]) return { status: 'missing', data: [] };
    load(id);
    return store[id];
  }

  window.dash = {
    data,
    onData(fn) { listeners.push(fn); try { fn(); } catch (e) { console.error(e); } },
    calc(id, spec) { calcs[id] = { inputs: spec.inputs, fn: spec.fn }; },
    loader() {},
    params() { return { ...params }; },
    setParams(p) { params = { ...params, ...p }; notify(); },
    resetParams() { params = { ...DEFAULT_PARAMS }; notify(); },
    setLink(name) { history.replaceState(null, '', '#' + name); },
    refresh() {},
    colors: ['#2f6fdb', '#d9534f', '#2a9d8f', '#e9a03b', '#8e6cc9', '#9aa5b1', '#b5651d', '#4c9f38'],
  };

  let t;
  window.addEventListener('resize', () => { clearTimeout(t); t = setTimeout(notify, 120); });
})();
