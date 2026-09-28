import type { Root, RootContent, PhrasingContent } from 'mdast';

const marker = /\[(S\d+)\]/gi;

function link(id: string): PhrasingContent {
  return { type: 'link', url: `#evidence-${id.toUpperCase()}`,
    children: [{ type: 'text', value: id.toUpperCase() }] };
}

// Run after remark-math: Markdown links inserted before parsing would corrupt
// math source. Code/link nodes are deliberately not traversed.
export default function remarkEvidenceCitations() {
  return (tree: Root) => {
    function transform(nodes: RootContent[]): RootContent[] {
      return nodes.flatMap((node): RootContent[] => {
        if (node.type === 'text') {
          const parts: PhrasingContent[] = [];
          let start = 0;
          for (const match of node.value.matchAll(marker)) {
            if (match.index! > start) parts.push({ type: 'text', value: node.value.slice(start, match.index) });
            parts.push(link(match[1]));
            start = match.index! + match[0].length;
          }
          if (!parts.length) return [node];
          if (start < node.value.length) parts.push({ type: 'text', value: node.value.slice(start) });
          return parts;
        }
        if (node.type === 'math' || node.type === 'inlineMath') {
          const ids = [...new Set([...node.value.matchAll(marker)].map(m => m[1].toUpperCase()))];
          if (!ids.length) return [node];
          node.value = node.value.replace(marker, '').trim();
          const mathText = { type: 'text' as const, value: node.value };
          node.data = { ...node.data, hChildren: node.type === 'math'
            ? [{ type: 'element', tagName: 'code', properties: { className: ['language-math', 'math-display'] }, children: [mathText] }]
            : [mathText] };
          const links = ids.map(link);
          return node.type === 'math'
            ? [node, { type: 'paragraph', children: links }]
            : [node, { type: 'text', value: ' ' }, ...links];
        }
        if ('children' in node && node.type !== 'link' && node.type !== 'linkReference') {
          // Preserve the parent's kind; replacements retain the corresponding
          // block/phrasing category (math -> math+paragraph, inline -> phrasing).
          node.children = transform(node.children) as typeof node.children;
        }
        return [node];
      });
    }
    tree.children = transform(tree.children) as Root['children'];
  };
}
