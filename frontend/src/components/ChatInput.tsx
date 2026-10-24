import { FormEvent, KeyboardEvent, useState } from "react";
import { MAX_MESSAGE_LENGTH } from "../services/types";

interface Props {
  onSend: (text: string) => Promise<boolean>;
  disabled: boolean;
  disabledReason?: string;
}

/** The prompt box and send button. Enter sends; Shift+Enter adds a new line. */
export function ChatInput({ onSend, disabled, disabledReason }: Props) {
  const [text, setText] = useState("");
  const canSend = !disabled && text.trim().length > 0;

  async function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!canSend) return;
    const value = text;
    setText("");
    const ok = await onSend(value);
    if (!ok) setText(value); // keep the text so the user can retry
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void submit();
    }
  }

  return (
    <form className="chat-input" onSubmit={submit}>
      <label htmlFor="chat-message" className="visually-hidden">
        Message to the agent
      </label>
      <textarea
        id="chat-message"
        rows={2}
        value={text}
        maxLength={MAX_MESSAGE_LENGTH}
        placeholder={disabledReason ?? "Describe what to build, e.g. “Create a blog”"}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={disabled}
      />
      <button type="submit" disabled={!canSend}>
        Send
      </button>
    </form>
  );
}
