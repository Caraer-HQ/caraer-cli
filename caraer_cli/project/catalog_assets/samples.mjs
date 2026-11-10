/** Stable fixtures; explicit defaults (including false and zero) always win. */
export function sampleFields(schema = []) {
  const out = {};
  for (const field of schema) {
    if (field.group && Array.isArray(field.fields)) { Object.assign(out, sampleFields(field.fields)); continue; }
    if (!field.name) continue;
    if (Object.hasOwn(field, 'defaultValue')) {
      out[field.name] = field.defaultValue;
      continue;
    }
    switch (String(field.type).toLowerCase()) {
      case 'single_line': case 'multi_line': case 'string': case 'text': case 'textarea': case 'richtext': case 'markdown':
        out[field.name] = /title|heading/i.test(field.name) ? 'Discover what comes next' :
          /url|link|href/i.test(field.name) ? 'https://example.com/' :
          /button|label/i.test(field.name) ? 'Learn more' : 'Explore our story and discover new opportunities.';
        break;
      case 'switch': case 'boolean': out[field.name] = true; break;
      case 'single_select': out[field.name] = field.options?.[0]?.name ?? field.options?.[0]?.value ?? ''; break;
      case 'object_single_select': out[field.name] = 'sample'; break;
      case 'form_single_select': out[field.name] = 'sample-form'; break;
      case 'property_single_select': out[field.name] = field.name.replace(/_property$/, ''); break;
      case 'property_multi_select': out[field.name] = []; break;
      case 'multi_select': out[field.name] = []; break;
      case 'repeatable': out[field.name] = Array.from({ length: Math.min(20, Math.max(field.min ?? 0, Math.min(3, field.max ?? 3))) }, () => sampleFields(field.itemFields)); break;
      case 'image': out[field.name] = 'data:image/svg+xml,' + encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><rect width="1200" height="800" fill="#dce5e9"/><circle cx="850" cy="240" r="110" fill="#b2c9ca"/><path d="M0 800L400 280L850 800" fill="#89a6ad"/></svg>'); break;
      case 'number': case 'integer': out[field.name] = 3; break;
    }
  }
  return out;
}

export function sampleRecords(query = {}) {
  const image = sampleFields([{name:'image',type:'IMAGE'}]).image;
  const records = Array.from({length:3}, (_, index) => {
    const properties = {title:`Our story ${index + 1}`, heading:`Our story ${index + 1}`, image,
      excerpt:'Discover our team and the opportunities ahead.', tag:'Our team', description:'Explore what comes next.'};
    return {uuid:`sample-${index}`,url:'#',properties,parsedProperties:properties};
  });
  return {records:records.slice(0, Math.min(3, query.limit || 3)),total:3,filterOptions:[{name:'Our team',label:'Our team'}]};
}

export function sampleForm() {
  return {uuid:'sample-form',name:'sample-form',label:'Get in touch',wizard:false,submitLabel:'Send message',steps:[{fields:[
    {uuid:'sample-name',name:'name',label:'Your name',type:'string',required:true},
    {uuid:'sample-email',name:'email',label:'Email address',type:'string',format:'email',required:true},
    {uuid:'sample-message',name:'message',label:'Message',type:'string',format:'multiline'},
  ]}]};
}
