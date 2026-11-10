import { lookup } from 'node:dns/promises';
import { request } from 'node:https';
import { BlockList, isIP } from 'node:net';

const denied = new BlockList();
const deniedV6 = new BlockList();
for (const [address, prefix] of [['0.0.0.0',8],['10.0.0.0',8],['100.64.0.0',10],['127.0.0.0',8],['169.254.0.0',16],['172.16.0.0',12],['192.0.0.0',24],['192.168.0.0',16],['198.18.0.0',15],['224.0.0.0',4],['240.0.0.0',4]]) denied.addSubnet(address,prefix,'ipv4');
for (const [address, prefix] of [['::',128],['::1',128],['::ffff:0:0',96],['fc00::',7],['fe80::',10],['ff00::',8]]) deniedV6.addSubnet(address,prefix,'ipv6');
export function publicAddress(address) {
  const family=isIP(address);
  return family === 4 ? !denied.check(address, 'ipv4') : family === 6 && !deniedV6.check(address, 'ipv6');
}

/** Pin the validated address, including on redirects, rather than letting Chromium resolve it again. */
export async function publicAsset(url, { method = 'GET', body, headers = {} } = {}) {
  if (!['GET', 'PUT'].includes(method)) throw new Error('Unsupported asset method');
  if (url.protocol !== 'https:' || url.username || url.password || (url.port && url.port !== '443')) throw new Error('Not a public asset');
  const addresses = await lookup(url.hostname, {all:true});
  if (!addresses.length || addresses.some(item => !publicAddress(item.address))) throw new Error('Private screenshot asset blocked');
  const chosen=addresses[0];
  return new Promise((resolve,reject) => {
    const req=request(url, { method, headers, lookup: (_host, options, callback) => options?.all ? callback(null,[chosen]) : callback(null,chosen.address,chosen.family) }, res => {
      const chunks=[]; let size=0;
      res.on('data', chunk => {
        size+=chunk.length;
        if (size > 16*1024*1024) req.destroy(new Error('Screenshot asset too large'));
        else chunks.push(chunk);
      });
      res.on('error',reject);
      res.on('end',() => resolve({status:res.statusCode,headers:{'content-type':String(res.headers['content-type'] || 'application/octet-stream'),
        'access-control-allow-origin':'*', ...(res.headers.location ? {location:res.headers.location} : {})},body:Buffer.concat(chunks)}));
    });
    req.setTimeout(10000,()=>req.destroy(new Error('Screenshot asset timed out')));
    req.on('error',reject); req.end(body);
  });
}

export async function publicAssetFollowingRedirects(url) {
  for (let hop = 0; hop < 6; hop++) {
    const response = await publicAsset(url);
    if (![301, 302, 303, 307, 308].includes(response.status)) return response;
    if (!response.headers.location) throw new Error('Invalid asset redirect');
    url = new URL(response.headers.location, url);
  }
  throw new Error('Too many asset redirects');
}
