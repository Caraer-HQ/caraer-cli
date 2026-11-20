import { pagePath, shareMetadata, type Draft, type PageSeo } from './page-document';

type SeoTextKey = Exclude<keyof PageSeo, 'noIndex'>;
type Platform = 'google' | 'facebook' | 'meta' | 'x' | 'tiktok';
const platformNotes: Record<Platform, string> = {
  google: 'Google can display a different title or description in search results.',
  facebook: 'Example Facebook link card. The published preview depends on Facebook’s crawler and cache.',
  meta: 'Example Threads link card. Meta may display the link differently across apps.',
  x: 'Example X link card based on the Open Graph metadata supported by Caraer.',
  tiktok: 'Example only. TikTok does not consistently display an external link card.',
};

export function mountPageMetadata(
  root: HTMLElement, current: () => Draft, save: () => void,
) {
  const get = <T extends HTMLElement>(id: string) => root.querySelector<T>('#' + id)!;
  const excerpt = get<HTMLTextAreaElement>('draft-excerpt');
  const noIndex = get<HTMLInputElement>('seo-no-index');
  const canonical = get<HTMLInputElement>('seo-canonical');
  const textControls: Record<SeoTextKey, HTMLInputElement | HTMLTextAreaElement> = {
    title: get<HTMLInputElement>('seo-title'),
    description: get<HTMLTextAreaElement>('seo-description'),
    image: get<HTMLInputElement>('seo-image'),
    canonical,
  };
  const dialog = get<HTMLDialogElement>('share-preview');
  const platform = get<HTMLSelectElement>('share-platform');
  const card = get('share-card');
  const image = get<HTMLImageElement>('share-card-image');
  const heading = get('share-card-title');
  const description = get('share-card-description');
  const address = get('share-card-url');
  const note = get('share-preview-note');

  for (const key of Object.keys(textControls) as SeoTextKey[]) {
    const input = textControls[key];
    input.addEventListener('input', () => {
      const seo = (current().seo ??= {});
      seo[key] = input.value;
      save();
    });
  }
  excerpt.addEventListener('input', () => { current().excerpt = excerpt.value; save(); });
  noIndex.addEventListener('change', () => { (current().seo ??= {}).noIndex = noIndex.checked; save(); });

  function renderCard() {
    const target = platform.value as Platform;
    const meta = shareMetadata(current());
    const url = meta.canonical ? new URL(meta.canonical) : null;
    card.dataset.platform = target;
    heading.textContent = meta.title;
    description.textContent = meta.description;
    description.hidden = !meta.description;
    address.textContent = !url ? pagePath(current().slug)
      : target === 'google' ? url.hostname + (url.pathname === '/' ? '' : url.pathname.replaceAll('/', ' › '))
      : url.hostname;
    const showImage = Boolean(meta.image && target !== 'google');
    image.hidden = !showImage;
    if (showImage) image.src = meta.image;
    else image.removeAttribute('src');
    note.textContent = target === 'google' && current().seo?.noIndex
      ? 'Search indexing is disabled for this page. This is an example snippet.'
      : platformNotes[target];
  }

  image.addEventListener('error', () => { image.hidden = true; });
  platform.addEventListener('change', renderCard);
  get('open-share-preview').addEventListener('click', () => {
    renderCard();
    dialog.showModal();
  });

  return () => {
    const draft = current();
    excerpt.value = draft.excerpt ?? '';
    noIndex.checked = draft.seo?.noIndex ?? false;
    for (const key of Object.keys(textControls) as SeoTextKey[]) textControls[key].value = draft.seo?.[key] ?? '';
  };
}
