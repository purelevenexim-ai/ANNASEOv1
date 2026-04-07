import { useEffect, useRef } from "react"
import { useEditor, EditorContent } from "@tiptap/react"
import StarterKit from "@tiptap/starter-kit"
import Image from "@tiptap/extension-image"
import Placeholder from "@tiptap/extension-placeholder"
import CharacterCount from "@tiptap/extension-character-count"
import Link from "@tiptap/extension-link"
import TextAlign from "@tiptap/extension-text-align"
import Underline from "@tiptap/extension-underline"
import Highlight from "@tiptap/extension-highlight"
import { T, api } from "../App"

// ── Image upload button ───────────────────────────────────────────────────────
function ImageUploadBtn({ editor, articleId }) {
  const inputRef = useRef()

  const uploadImage = (file) => {
    const reader = new FileReader()
    reader.onload = async (e) => {
      const base64 = e.target.result
      try {
        if (articleId) {
          const res = await api.post(`/api/content/${articleId}/images`, {
            base64,
            filename: file.name || "image.jpg",
          })
          if (res?.url) {
            editor.chain().focus().setImage({ src: res.url, alt: file.name }).run()
            return
          }
        }
      } catch (_) {
        // fall through to base64 inline
      }
      editor.chain().focus().setImage({ src: base64 }).run()
    }
    reader.readAsDataURL(file)
  }

  return (
    <>
      <button
        type="button"
        onMouseDown={e => e.preventDefault()}
        onClick={() => inputRef.current?.click()}
        title="Insert image"
        style={toolbarBtnStyle(false)}
      >
        Image
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        style={{ display: "none" }}
        onChange={e => { if (e.target.files?.[0]) uploadImage(e.target.files[0]) }}
      />
    </>
  )
}

// ── Toolbar button style helper ───────────────────────────────────────────────
function toolbarBtnStyle(isActive) {
  return {
    padding: "4px 9px",
    background: isActive ? T.purpleLight : "transparent",
    color: isActive ? T.purple : T.textSoft,
    border: "none",
    cursor: "pointer",
    borderRadius: 6,
    fontSize: 12,
    fontWeight: isActive ? 600 : 400,
    lineHeight: 1.4,
    fontFamily: "inherit",
  }
}

// ── Separator ─────────────────────────────────────────────────────────────────
function Sep() {
  return <div style={{ width: 1, background: T.border, margin: "0 4px", alignSelf: "stretch" }} />
}

// ── Editor toolbar ────────────────────────────────────────────────────────────
function EditorToolbar({ editor, articleId }) {
  if (!editor) return null

  const btn = (label, action, isActive, title) => (
    <button
      key={label}
      type="button"
      onMouseDown={e => e.preventDefault()}
      onClick={action}
      title={title || label}
      style={toolbarBtnStyle(isActive)}
    >
      {label}
    </button>
  )

  return (
    <div style={{
      display: "flex",
      gap: 2,
      alignItems: "center",
      padding: "6px 10px",
      flexWrap: "wrap",
      background: "#F2F2F7",
      borderRadius: "12px 12px 0 0",
      border: `1px solid ${T.border}`,
      borderBottom: "none",
      position: "sticky",
      top: 0,
      zIndex: 5,
    }}>
      {btn("B", () => editor.chain().focus().toggleBold().run(), editor.isActive("bold"), "Bold")}
      {btn("I", () => editor.chain().focus().toggleItalic().run(), editor.isActive("italic"), "Italic")}
      {btn("U", () => editor.chain().focus().toggleUnderline().run(), editor.isActive("underline"), "Underline")}
      <Sep />
      {btn("H1", () => editor.chain().focus().toggleHeading({ level: 1 }).run(), editor.isActive("heading", { level: 1 }), "Heading 1")}
      {btn("H2", () => editor.chain().focus().toggleHeading({ level: 2 }).run(), editor.isActive("heading", { level: 2 }), "Heading 2")}
      {btn("H3", () => editor.chain().focus().toggleHeading({ level: 3 }).run(), editor.isActive("heading", { level: 3 }), "Heading 3")}
      <Sep />
      {btn("• List", () => editor.chain().focus().toggleBulletList().run(), editor.isActive("bulletList"), "Bullet list")}
      {btn("1. List", () => editor.chain().focus().toggleOrderedList().run(), editor.isActive("orderedList"), "Numbered list")}
      {btn("❝", () => editor.chain().focus().toggleBlockquote().run(), editor.isActive("blockquote"), "Blockquote")}
      {btn("—", () => editor.chain().focus().setHorizontalRule().run(), false, "Horizontal rule")}
      <Sep />
      {btn("Mark", () => editor.chain().focus().toggleHighlight().run(), editor.isActive("highlight"), "Highlight")}
      {btn("Code", () => editor.chain().focus().toggleCode().run(), editor.isActive("code"), "Inline code")}
      <Sep />
      {btn("↩ Undo", () => editor.chain().focus().undo().run(), false, "Undo")}
      {btn("↪ Redo", () => editor.chain().focus().redo().run(), false, "Redo")}
      <Sep />
      <ImageUploadBtn editor={editor} articleId={articleId} />
    </div>
  )
}

// ── Main Tiptap editor ────────────────────────────────────────────────────────
export default function TiptapEditor({ content, onChange, onEditorReady, placeholder, articleId }) {
  const prevContent = useRef(content)

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        bulletList: { keepMarks: true },
        orderedList: { keepMarks: true },
      }),
      Image.configure({ inline: false, allowBase64: true }),
      Placeholder.configure({ placeholder: placeholder || "Start writing your article here..." }),
      CharacterCount,
      Link.configure({ openOnClick: false, autolink: true }),
      TextAlign.configure({ types: ["heading", "paragraph"] }),
      Underline,
      Highlight.configure({ multicolor: false }),
    ],
    content: content || "",
    onUpdate: ({ editor }) => {
      onChange?.(editor.getHTML())
    },
    editorProps: {
      attributes: {
        class: "tiptap-article-body",
      },
    },
  })

  // Notify parent when editor is ready
  useEffect(() => {
    if (editor && onEditorReady) onEditorReady(editor)
  }, [editor]) // eslint-disable-line

  // Sync externally-changed content (e.g. after AI rewrite)
  useEffect(() => {
    if (!editor) return
    if (content !== prevContent.current) {
      prevContent.current = content
      const current = editor.getHTML()
      if (content !== current) {
        editor.commands.setContent(content || "", false)
      }
    }
  }, [content, editor])

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
      <EditorToolbar editor={editor} articleId={articleId} />

      {/* Editor body */}
      <div style={{
        flex: 1,
        background: "#fff",
        border: `1px solid ${T.border}`,
        borderRadius: "0 0 12px 12px",
        overflowY: "auto",
      }}>
        <style>{`
          .tiptap-article-body {
            font-family: 'Lora', Georgia, serif;
            font-size: 17px;
            line-height: 1.85;
            color: #1a1a1a;
            max-width: 780px;
            margin: 0 auto;
            padding: 40px 32px 80px;
            min-height: 560px;
            outline: none;
          }
          .tiptap-article-body h1 {
            font-family: 'DM Serif Display', Georgia, serif;
            font-size: 2em;
            font-weight: 400;
            line-height: 1.2;
            margin: 1.4em 0 0.5em;
            color: #111;
          }
          .tiptap-article-body h2 {
            font-family: 'DM Serif Display', Georgia, serif;
            font-size: 1.5em;
            font-weight: 400;
            line-height: 1.25;
            margin: 1.3em 0 0.4em;
            color: #1a1a1a;
          }
          .tiptap-article-body h3 {
            font-family: 'Plus Jakarta Sans', sans-serif;
            font-size: 1.1em;
            font-weight: 600;
            margin: 1.1em 0 0.3em;
            color: #222;
          }
          .tiptap-article-body p {
            margin: 0 0 1.1em;
          }
          .tiptap-article-body ul, .tiptap-article-body ol {
            padding-left: 1.4em;
            margin: 0.6em 0 1em;
          }
          .tiptap-article-body li {
            margin-bottom: 0.3em;
          }
          .tiptap-article-body blockquote {
            border-left: 3px solid #7F77DD;
            margin: 1em 0;
            padding: 8px 16px;
            background: #EEEDFE;
            border-radius: 0 8px 8px 0;
            font-style: italic;
            color: #534AB7;
          }
          .tiptap-article-body code {
            background: #f3f3f3;
            padding: 1px 5px;
            border-radius: 4px;
            font-size: 0.9em;
            font-family: 'JetBrains Mono', 'Fira Code', monospace;
          }
          .tiptap-article-body pre {
            background: #0f1117;
            color: #e2e8f0;
            padding: 16px;
            border-radius: 10px;
            overflow-x: auto;
            font-size: 13px;
            line-height: 1.6;
            margin: 1em 0;
          }
          .tiptap-article-body img {
            max-width: 100%;
            border-radius: 10px;
            margin: 1em 0;
            display: block;
          }
          .tiptap-article-body hr {
            border: none;
            border-top: 1px solid rgba(0,0,0,0.1);
            margin: 2em 0;
          }
          .tiptap-article-body mark {
            background: #FFF3AA;
            border-radius: 2px;
            padding: 0 2px;
          }
          .tiptap-article-body a {
            color: #7F77DD;
            text-decoration: underline;
            text-underline-offset: 2px;
          }
          .tiptap-article-body p.is-editor-empty:first-child::before {
            content: attr(data-placeholder);
            float: left;
            color: #aaa;
            pointer-events: none;
            height: 0;
          }
        `}</style>
        <EditorContent editor={editor} style={{ height: "100%" }} />
      </div>

      {/* Word count */}
      {editor && (
        <div style={{ fontSize: 10, color: T.textSoft, padding: "4px 12px", textAlign: "right", borderTop: `1px solid ${T.border}` }}>
          {editor.storage.characterCount.words()} words · {editor.storage.characterCount.characters()} chars
        </div>
      )}
    </div>
  )
}
