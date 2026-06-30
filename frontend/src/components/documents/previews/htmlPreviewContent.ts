export function prepareHtmlPreviewContent(content: string): string {
  if (/<base\b/i.test(content)) {
    return content;
  }

  const baseTag = '<base href="about:srcdoc" />';
  if (/<head\b[^>]*>/i.test(content)) {
    return content.replace(/<head\b([^>]*)>/i, `<head$1>${baseTag}`);
  }

  if (/<html\b[^>]*>/i.test(content)) {
    return content.replace(
      /<html\b([^>]*)>/i,
      `<html$1><head>${baseTag}</head>`,
    );
  }

  return `<head>${baseTag}</head>${content}`;
}
