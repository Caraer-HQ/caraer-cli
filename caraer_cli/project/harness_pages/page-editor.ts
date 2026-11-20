import { toCaraerPageDocument, type Draft } from './page-document';
import { mountPageMetadata } from './page-metadata-editor';
import { materializeModuleFields, recordValue, type Field, type Values } from './page-fields';
type Module = { name: string; label: string; kind: string; fields: Field[]; defaults: Values };

export function mountPageEditor(root: HTMLElement) {
  const get = <T extends HTMLElement>(id: string) => root.querySelector<T>('#' + id)!;
  const library: Module[] = JSON.parse(root.dataset.library ?? '[]');
  const appName = root.dataset.app!;
  const catalog = new Map(library.map(module => [module.name, module]));
  const storageKey = 'caraer.page-drafts.v1.' + root.dataset.workspace;
  const picker = get<HTMLSelectElement>('draft-picker');
  const title = get<HTMLInputElement>('draft-title');
  const slug = get<HTMLInputElement>('draft-slug');
  const sections = get<HTMLOListElement>('sections');
  const modulePicker = get<HTMLSelectElement>('module-picker');
  const form = get<HTMLFormElement>('preview-form');
  const payload = form.querySelector<HTMLInputElement>('[name=draft]')!;
  const status = get('draft-status');
  let active = 0;
  let drafts: Draft[] = [{ title: 'Untitled page', slug: '/', sections: [] }];
  let saved: { active: number; drafts: Draft[] } | undefined;
  try { saved = JSON.parse(localStorage.getItem(storageKey) ?? 'null') ?? undefined; } catch { /* Start with the supplied drafts. */ }
  if (Array.isArray(saved?.drafts) && saved.drafts.length && saved.drafts.every(page =>
    recordValue(page) && typeof page.title === 'string' && typeof page.slug === 'string'
    && Array.isArray(page.sections) && page.sections.every(section =>
      recordValue(section) && typeof section.name === 'string' && recordValue(section.fields),
    ),
  )) {
    drafts = saved.drafts;
    active = Number.isInteger(saved.active) && drafts[saved.active] ? saved.active : 0;
  }
  for (const draft of drafts) {
    for (const section of draft.sections) section.id ??= crypto.randomUUID();
  }
  const current = () => drafts[active];
  const initialPath = new URL(location.href).searchParams.get('path');
  const initialIndex = drafts.findIndex(page => page.slug === initialPath);
  if (initialIndex >= 0) active = initialIndex;
  const updatePayload = () => { payload.value = JSON.stringify(current()); };

  function save(changed = true) {
    if (changed) current().revision = (current().revision ?? 0) + 1;
    updatePayload();
    try {
      localStorage.setItem(storageKey, JSON.stringify({ active, drafts }));
      status.textContent = 'Saved locally';
    } catch { status.textContent = 'Could not save locally. Export your draft.'; }
  }
  const loadMetadata = mountPageMetadata(root, current, save);

  function refreshPreview() {
    updatePayload();
    form.requestSubmit();
  }

  function button(text: string, action: () => void, label = text) {
    const element = document.createElement('button');
    element.type = 'button';
    element.textContent = text;
    element.setAttribute('aria-label', label);
    element.addEventListener('click', action);
    return element;
  }

  function fieldControls(definitions: Field[], values: Values, defaults: Values, onEdit: () => void): DocumentFragment {
    const fragment = document.createDocumentFragment();
    for (const { name, label, type, group, fields, itemFields, options, defaultValue } of definitions) {
      if (fields) {
        const fieldset = document.createElement('fieldset');
        const legend = document.createElement('legend');
        legend.textContent = group ?? label ?? '';
        fieldset.append(legend, fieldControls(fields, values, defaults, onEdit));
        fragment.append(fieldset);
        continue;
      }
      if (!name) continue;
      const caption = label ?? name;
      const value = values[name] ?? defaults[name] ?? defaultValue;
      if (type === 'REPEATABLE' && itemFields) {
        const fieldset = document.createElement('fieldset');
        const legend = document.createElement('legend');
        legend.textContent = caption;
        const items: Values[] = Array.isArray(value) ? structuredClone(value) : [];
        const commit = () => { values[name] = items; onEdit(); };
        function showItems() {
          fieldset.replaceChildren(legend);
          items.forEach((item, index) => {
            const row = document.createElement('details');
            const summary = document.createElement('summary');
            summary.textContent = caption + ' ' + (index + 1);
            row.append(summary, fieldControls(itemFields!, item, {}, commit), button('Remove item', () => {
              items.splice(index, 1);
              commit();
              showItems();
            }));
            fieldset.append(row);
          });
          const add = button('Add item', () => {
            items.push({});
            commit();
            showItems();
            const latest = fieldset.querySelector('details:last-of-type');
            if (latest) latest.open = true;
          });
          add.disabled = items.length >= 100;
          fieldset.append(add);
        }
        showItems();
        fragment.append(fieldset);
        continue;
      }

      const wrapper = document.createElement('label');
      wrapper.className = 'field';
      wrapper.textContent = caption;
      if (type === 'SWITCH') {
        const input = document.createElement('input');
        input.type = 'checkbox';
        input.checked = value === true;
        input.addEventListener('change', () => { values[name] = input.checked; onEdit(); });
        wrapper.append(input);
      } else if (['SINGLE_SELECT', 'SINGLE_LINE', 'MULTI_LINE', 'COLOR', 'IMAGE'].includes(type ?? '')) {
        const input = type === 'SINGLE_SELECT' ? document.createElement('select')
          : type === 'MULTI_LINE' ? document.createElement('textarea') : document.createElement('input');
        if (input instanceof HTMLSelectElement) {
          for (const option of options ?? []) input.add(new Option(option.label, option.name));
        }
        if (type === 'IMAGE' && input instanceof HTMLInputElement) input.placeholder = 'Image URL';
        input.value = typeof value === 'string' ? value : '';
        input.addEventListener('input', () => { values[name] = input.value; onEdit(); });
        wrapper.append(input);
      } else {
        const input = document.createElement('textarea');
        input.placeholder = 'JSON value';
        input.value = value === undefined ? '' : JSON.stringify(value, null, 2);
        input.addEventListener('change', () => {
          try {
            values[name] = input.value.trim() ? JSON.parse(input.value) : null;
            input.setCustomValidity('');
            onEdit();
          } catch {
            input.setCustomValidity('Enter a valid JSON value.');
            input.reportValidity();
          }
        });
        wrapper.append(input);
      }
      fragment.append(wrapper);
    }
    return fragment;
  }

  function renderSections(openIndex = -1) {
    const items = current().sections;
    sections.replaceChildren(...items.map((section, index) => {
      const module = catalog.get(section.name);
      const label = module?.label ?? section.name;
      const li = document.createElement('li');
      li.className = 'section-row';
      const details = document.createElement('details');
      const summary = document.createElement('summary');
      summary.textContent = label;
      details.open = index === openIndex;
      details.append(summary);
      if (module) details.append(fieldControls(module.fields, section.fields, module.defaults, save));
      function move(to: number, action: number) {
        [items[to], items[index]] = [items[index], items[to]];
        update(to);
        sections.children[to]?.querySelectorAll('button[data-order]')[action]?.focus();
      }
      const up = button('↑', () => move(index - 1, 0), 'Move ' + label + ' up');
      const down = button('↓', () => move(index + 1, 1), 'Move ' + label + ' down');
      up.disabled = index === 0;
      down.disabled = index === items.length - 1;
      up.dataset.order = down.dataset.order = '';
      const remove = button('×', () => {
        items.splice(index, 1);
        update();
        (sections.children[index] ?? sections.children[index - 1])?.querySelector('summary')?.focus();
      }, 'Remove ' + label);
      li.append(details, up, down, remove);
      return li;
    }));
    get<HTMLButtonElement>('add-section').disabled = items.length >= 40 || !modulePicker.value;
  }

  function update(openIndex = -1, changed = true) {
    renderSections(openIndex);
    save(changed);
    refreshPreview();
  }

  function loadDraft() {
    picker.replaceChildren(...drafts.map((page, index) => new Option(page.title, String(index))));
    picker.value = String(active);
    title.value = current().title;
    slug.value = current().slug;
    loadMetadata();
    const url = new URL(location.href);
    url.searchParams.set('path', current().slug);
    history.replaceState(null, '', url);
    update(-1, false);
  }

  picker.addEventListener('change', () => { active = Number(picker.value); loadDraft(); });
  title.addEventListener('input', () => {
    current().title = title.value;
    picker.options[active].text = title.value || 'Untitled page';
    save();
  });
  slug.addEventListener('input', () => {
    current().slug = slug.value;
    loadMetadata();
    save();
  });
  get('new-draft').addEventListener('click', () => {
    let nextSlug = '/new-page';
    for (let i = 2; drafts.some(draft => draft.slug === nextSlug); i++) nextSlug = '/new-page-' + i;
    active = drafts.push({ title: 'New page', slug: nextSlug, sections: [] }) - 1;
    loadDraft();
    title.select();
  });
  for (const module of library.filter(module => module.kind === 'section')) {
    modulePicker.add(new Option(module.label, module.name));
  }
  get('add-section').addEventListener('click', () => {
    const index = current().sections.push({ id: crypto.randomUUID(), name: modulePicker.value, fields: {} }) - 1;
    update(index);
    sections.children[index]?.querySelector('summary')?.focus();
  });
  get('export-draft').addEventListener('click', () => {
    const exported = toCaraerPageDocument(current(), appName, section => {
      const module = catalog.get(section.name);
      return module ? materializeModuleFields(module.fields, section.fields) : section.fields;
    });
    const file = new Blob([JSON.stringify(exported, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(file);
    const link = document.createElement('a');
    link.href = url;
    link.download = (current().slug.replace(/[^a-z0-9-]+/gi, '-').replace(/^-|-$/g, '') || 'home') + '.json';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  loadDraft();
}
