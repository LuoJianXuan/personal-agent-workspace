import { useState } from "react";

// The activity calendar formats each picture as its own HTML tag on a line.
const imageLine = /^[\t ]*<img[\t ]+src[\t ]*=[\t ]*(?:"([^"\r\n]+)"|'([^'\r\n]+)')[^>\r\n]*>[\t ]*\r?$/im;

function activityImageURL(source: string | undefined) {
  if (!source) return undefined;
  try {
    const url = new URL(source);
    if (url.origin !== "https://cms-cdn.mcd.cn" || url.username || url.password || url.search || url.hash) {
      return undefined;
    }
    if (/^\/img\/[a-z0-9_./-]+\.(?:png|jpe?g|webp)$/i.test(url.pathname)) {
      return url.href;
    }
  } catch {
    // An unrecognized source stays in the original result text.
  }
  return undefined;
}

export function activityImageFromTag(text: string) {
  const match = imageLine.exec(text);
  return match ? activityImageURL(match[1] ?? match[2]) : undefined;
}

export function ActivityImage({ src, alt = "麦当劳活动图片" }: { src: string; alt?: string }) {
  const [failed, setFailed] = useState(false);
  return failed ? <p className="tool-result-image-error">活动图片暂时无法加载</p> : (
    <img
      className="tool-result-image"
      src={src}
      alt={alt}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}

export function ToolResult({ text }: { text: string }) {
  const previews = [];
  let from = 0;
  for (const match of text.matchAll(new RegExp(imageLine, "gim"))) {
    const src = activityImageURL(match[1] ?? match[2]);
    if (!src) continue;
    const preceding = text.slice(from, match.index);
    if (preceding.trim()) previews.push(<pre key={from}>{preceding.trim()}</pre>);
    previews.push(<ActivityImage key={`${match.index}:${src}`} src={src} />);
    from = match.index + match[0].length;
  }
  if (!previews.length) return <pre>{text}</pre>;
  const remaining = text.slice(from);
  if (remaining.trim()) previews.push(<pre key={from}>{remaining.trim()}</pre>);
  return <div className="tool-result-with-images">{previews}</div>;
}
