export type PageSeo = {
  title?: string;
  description?: string;
  image?: string;
  canonical?: string;
  noIndex?: boolean;
};

export type Section = {
  id?: string;
  name: string;
  fields: Record<string, unknown>;
  hidden?: boolean | null;
};

export type Draft = {
  title: string;
  slug: string;
  sections: Section[];
  revision?: number;
  excerpt?: string;
  seo?: PageSeo;
  css?: string | null;
  headJs?: string | null;
  bodyJs?: string | null;
  relatedToTemplate?: boolean;
};

export function httpUrl(value: unknown) {
  if (typeof value !== 'string' || !value.trim()) return '';
  try {
    const url = new URL(value.trim());
    return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : '';
  } catch { return ''; }
}

export function pagePath(slug: string) {
  return '/' + slug.split('/').map(segment => segment.trim()).filter(Boolean).join('/');
}

export function shareMetadata(draft: Draft) {
  const seo = draft.seo ?? {};
  return {
    title: seo.title?.trim() || draft.title.trim() || 'Untitled page',
    description: seo.description?.trim() || '',
    image: httpUrl(seo.image),
    canonical: httpUrl(seo.canonical),
  };
}

export function toCaraerPageDocument(
  draft: Draft,
  appName: string,
  resolveFields: (section: Section) => Record<string, unknown>,
) {
  const share = shareMetadata(draft);
  return {
    version: 2,
    revision: draft.revision ?? 0,
    modules: draft.sections.map(section => ({
      id: section.id,
      module: appName + '/' + section.name,
      fields: resolveFields(section),
      hidden: section.hidden ?? null,
    })),
    seo: {
      title: share.title,
      description: share.description,
      ...(share.image && { image: share.image }),
      ...(share.canonical && { canonical: share.canonical }),
      noIndex: draft.seo?.noIndex ?? false,
    },
    title: draft.title,
    slug: pagePath(draft.slug),
    excerpt: draft.excerpt?.trim() || null,
    css: draft.css ?? null,
    headJs: draft.headJs ?? null,
    bodyJs: draft.bodyJs ?? null,
    relatedToTemplate: draft.relatedToTemplate ?? false,
  };
}
