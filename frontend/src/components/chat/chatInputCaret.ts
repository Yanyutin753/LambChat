export function getComposerCaretBoundary(editor: HTMLElement): {
  atStart: boolean;
  atEnd: boolean;
} {
  const selection = editor.ownerDocument.defaultView?.getSelection();
  const anchorNode = selection?.anchorNode;
  if (!selection?.isCollapsed || !anchorNode || !editor.contains(anchorNode)) {
    return { atStart: false, atEnd: false };
  }

  try {
    const beforeCaret = editor.ownerDocument.createRange();
    beforeCaret.selectNodeContents(editor);
    beforeCaret.setEnd(anchorNode, selection.anchorOffset);

    const afterCaret = editor.ownerDocument.createRange();
    afterCaret.selectNodeContents(editor);
    afterCaret.setStart(anchorNode, selection.anchorOffset);

    return {
      atStart: beforeCaret.toString().length === 0,
      atEnd: afterCaret.toString().length === 0,
    };
  } catch {
    return { atStart: false, atEnd: false };
  }
}
