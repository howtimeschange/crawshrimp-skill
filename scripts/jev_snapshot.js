/* Atomic, code-owned control references. Model output never becomes executable JS. */
(options => {
  const root = document.querySelector(options.scope);
  const text = el => (el?.innerText || el?.textContent || '').replace(/\s+/g, ' ').trim();
  const visible = el => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const sensitive = el => el.matches('input[type=password],input[type=file]') ||
    /password|passwd|token|secret|otp|one.?time|credit.?card|card.?number|cvv/i.test(
      [el.name, el.id, el.autocomplete, el.getAttribute('aria-label')].join(' '));
  const dangerous = /\b(delete|remove|publish|submit|send|save|approve|authorize|transfer|refund|pay|purchase|confirm|checkout|buy|order now|add to cart|add to basket)\b|删除|发布|提交|发送|保存|批准|付款|支付|购买|确认/i;
  const label = el => el.getAttribute('aria-label') || text(el) || el.placeholder || el.title || el.name || el.tagName.toLowerCase();
  const context = el => text(el.closest('label,fieldset,[role=group],li') || el.parentElement).slice(0, 180);
  const nodeValue = el => sensitive(el) ? '[redacted]' : (el.value || '');
  const describe = el => JSON.stringify([label(el), nodeValue(el), !!el.checked, context(el)]);
  const old = window.__crawshrimpJev;
  const runtime = old?.document === document ? old : {document, serial: 0};
  const pageText = text(root).slice(0, options.textLimit || 5000);
  const bodyText = text(document.body).slice(0, 1600);
  const blocked = /captcha|slide.{0,30}puzzle|人机验证|滑块验证|请登录|需要登录|sign in to continue|login required/i.test(bodyText) ||
    /\/(?:verify\/captcha|buyer\/login)/.test(location.pathname);
  const unavailable = /page unavailable|temporarily unavailable|something went wrong|err_connection/i.test(bodyText) &&
    (bodyText.length < 1200 || /\/verify\/traffic\/error/.test(location.pathname));
  const nodes = new Map();
  const elements = [];
  if (root) {
    for (const el of root.querySelectorAll('button,a[href],input,textarea,select,[role=button],[role=tab],[role=checkbox]')) {
      if (elements.length >= 80) break;
      if (!visible(el) || el.disabled || el.closest('[aria-disabled=true],[inert]') || sensitive(el)) continue;
      const name = label(el).slice(0, 200);
      if (dangerous.test(name) || el.matches('input[type=submit]')) continue;
      const ref = `e${elements.length + 1}`;
      const operations = [];
      const isText = el.matches('textarea,input:not([type]),input[type=text],input[type=search],input[type=email],input[type=number]');
      if (isText && !el.readOnly) operations.push('TYPE_TEXT');
      else if (el.tagName === 'SELECT') operations.push('SELECT');
      else {
        const href = el.getAttribute('href');
        if (href && (new URL(el.href).origin !== location.origin || el.target === '_blank' || /^javascript:/i.test(href))) continue;
        operations.push('CLICK');
      }
      const item = {ref, name, role: el.getAttribute('role') || el.tagName.toLowerCase(),
        value: nodeValue(el), checked: !!el.checked, context: context(el), operations};
      if (el.tagName === 'SELECT' && el.options.length > 255) item.operations = [];
      if (el.tagName === 'SELECT') item.options = [...el.options].map((o, index) => ({
        ref: `${ref}:o${index}`, label: text(o), value: o.value, disabled: o.disabled || !!o.closest('optgroup[disabled]')
      })).filter(o => !o.disabled).slice(0, 255);
      nodes.set(ref, {el, signature: describe(el)});
      elements.push(item);
    }
  }
  const id = `${performance.timeOrigin}:${++runtime.serial}`;
  runtime.nodes = nodes;
  runtime.snapshotId = id;
  runtime.url = location.href;
  runtime.consumed = false;
  runtime.act = action => {
    if (runtime.consumed || action.snapshot_id !== runtime.snapshotId || runtime.document !== document || runtime.url !== location.href)
      return {ok: false, status: 'stale', executed: false};
    if (text(root).slice(0, options.textLimit || 5000) !== pageText ||
        [...nodes.values()].some(n => !n.el.isConnected || describe(n.el) !== n.signature))
      return {ok: false, status: 'stale', executed: false};
    const target = nodes.get(action.ref?.split(':')[0]);
    const el = target?.el;
    if (!el?.isConnected || !visible(el) || el.disabled || el.closest('[aria-disabled=true],[inert]') || sensitive(el) ||
        describe(el) !== target.signature || dangerous.test(label(el)))
      return {ok: false, status: 'stale', executed: false};
    const offered = elements.find(item => item.ref === action.ref?.split(':')[0]);
    if (!offered?.operations.includes(action.operation)) return {ok: false, status: 'invalid', executed: false};
    if (action.operation === 'SELECT' && !offered.options?.some(o => o.ref === action.ref && o.value === action.value))
      return {ok: false, status: 'stale', executed: false};
    el.scrollIntoView({block: 'center', inline: 'nearest', behavior: 'instant'});
    const r = el.getBoundingClientRect();
    const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    if (!hit || !el.contains(hit)) return {ok: false, status: 'covered', executed: false};
    // Consume before input. A lost response must never cause an automatic replay.
    runtime.consumed = true;
    if (action.operation === 'CLICK') el.click();
    else {
      if (typeof action.value !== 'string') return {ok: false, status: 'invalid', executed: false};
      const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype :
        el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, action.value);
      el.dispatchEvent(new Event('input', {bubbles: true}));
      el.dispatchEvent(new Event('change', {bubbles: true}));
    }
    return {ok: true, status: 'executed', executed: true};
  };
  window.__crawshrimpJev = runtime;
  return {snapshot_id: id, url: location.href, title: document.title, ready: document.readyState,
    text: pageText, elements, blocked, unavailable, scope_found: !!root};
})
