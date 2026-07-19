import { NextRequest, NextResponse } from "next/server";

// Cloudflare 官方 IP 网段（https://www.cloudflare.com/ips/）
const CF_CIDR_V4 = [
  "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22",
  "141.101.64.0/18", "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20",
  "197.234.240.0/22", "198.41.128.0/17", "162.158.0.0/15", "104.16.0.0/13",
  "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
];
const CF_CIDR_V6 = [
  "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32",
  "2405:8100::/32", "2a06:98c0::/29", "2c0f:f248::/32",
];

function parseCidrV4(cidr: string): [bigint, bigint] {
  const [ip, bits] = cidr.split("/");
  const p = ip.split(".").map(Number);
  const addr = BigInt((p[0] << 24) | (p[1] << 16) | (p[2] << 8) | p[3]);
  const mask = BigInt(0xffffffff) << BigInt(32 - Number(bits));
  return [addr & mask, mask];
}

function expandV6(ip: string): string {
  if (ip.includes("::")) {
    const [l, r] = ip.split("::");
    const left = l ? l.split(":") : [];
    const right = r ? r.split(":") : [];
    const fill = Array(8 - left.length - right.length).fill("0");
    return [...left, ...fill, ...right].map(g => g.padStart(4, "0")).join(":");
  }
  return ip.split(":").map(g => g.padStart(4, "0")).join(":");
}

function parseCidrV6(cidr: string): [bigint, bigint] {
  const [ip, bits] = cidr.split("/");
  const groups = expandV6(ip).split(":").map(g => parseInt(g, 16));
  let addr = 0n;
  for (const g of groups) addr = (addr << 16n) | BigInt(g);
  const mask = bits === "0" ? 0n
    : (((1n << 128n) - 1n) >> BigInt(128 - Number(bits))) << BigInt(128 - Number(bits));
  return [addr & mask, mask];
}

function ipv4ToInt(ip: string): bigint {
  const p = ip.split(".").map(Number);
  return BigInt((p[0] << 24) | (p[1] << 16) | (p[2] << 8) | p[3]);
}

function ipv6ToInt(ip: string): bigint {
  const groups = expandV6(ip).split(":").map(g => parseInt(g, 16));
  let n = 0n;
  for (const g of groups) n = (n << 16n) | BigInt(g);
  return n;
}

const PARSED_V4 = CF_CIDR_V4.map(parseCidrV4);
const PARSED_V6 = CF_CIDR_V6.map(parseCidrV6);

function isCloudflareIP(ip: string): boolean {
  if (!ip) return false;
  const v4mapped = ip.match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/i);
  const v4 = v4mapped ? v4mapped[1] : ip;
  if (/^\d+\.\d+\.\d+\.\d+$/.test(v4)) {
    const n = ipv4ToInt(v4);
    return PARSED_V4.some(([net, mask]) => (n & mask) === net);
  }
  if (ip.includes(":")) {
    try {
      const n = ipv6ToInt(ip);
      return PARSED_V6.some(([net, mask]) => (n & mask) === net);
    } catch { return false; }
  }
  return false;
}

// CF-Ray 格式：16 位十六进制-机场代码，例如 89ab12cd34ef5678-NRT
const CF_RAY_RE = /^[0-9a-f]{16}-[A-Z]{3,4}$/i;

const ENABLED = process.env.CF_IP_WHITELIST_ENABLED === "true";

function logAccess(verdict: "allow" | "block", reason: string, sourceIp: string, cfIp: string | null, cfRay: string | null, xff: string | null, url: string) {
  console.log(JSON.stringify({
    ts: new Date().toISOString(),
    event: "cf_whitelist",
    verdict,
    reason,
    source_ip: sourceIp,
    cf_connecting_ip: cfIp,
    cf_ray: cfRay,
    xff,
    url,
  }));
}

export function middleware(req: NextRequest) {
  if (!ENABLED) return NextResponse.next();

  const url = req.nextUrl.pathname;
  // X-Real-IP：由 Docker/nginx 反向代理注入的 socket 级连接 IP。
  // Next.js 15 移除了 req.ip，改从此头读取。
  // 注意：此头在 docker-compose.prod.yml 中 frontend 直接暴露 80 端口，
  // 前面若无 nginx 则此头为空——此时退化为仅校验 CF 头，仍有效防直连伪造。
  const sourceIp = req.headers.get("x-real-ip") ?? "";
  const cfConnectingIp = req.headers.get("cf-connecting-ip");
  const cfRay = req.headers.get("cf-ray");
  const xff = req.headers.get("x-forwarded-for");

  // 校验 1：source IP 在 Cloudflare CIDR 内（不可伪造，有值时才校验）
  // X-Real-IP 需上游 nginx 注入；直接暴露端口时为空，跳过此项退化为仅靠 CF 头。
  if (sourceIp && !isCloudflareIP(sourceIp)) {
    logAccess("block", "source_ip_not_cf", sourceIp, cfConnectingIp, cfRay, xff, url);
    return new NextResponse(null, { status: 403 });
  }
  // 校验 2：CF-Connecting-IP 存在（Cloudflare 必然注入，直连无此头）
  if (!cfConnectingIp) {
    logAccess("block", "no_cf_connecting_ip", sourceIp, cfConnectingIp, cfRay, xff, url);
    return new NextResponse(null, { status: 403 });
  }
  // 校验 3：CF-Ray 存在且格式正确（每个 Cloudflare 请求唯一生成）
  if (!cfRay || !CF_RAY_RE.test(cfRay)) {
    logAccess("block", "invalid_cf_ray", sourceIp, cfConnectingIp, cfRay, xff, url);
    return new NextResponse(null, { status: 403 });
  }

  logAccess("allow", "ok", sourceIp, cfConnectingIp, cfRay, xff, url);
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
