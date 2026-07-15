'use client';

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useTranslations } from 'next-intl';

interface ConfirmState {
  type: 'confirm';
  message: string;
  resolve: (v: boolean) => void;
}

interface PromptState {
  type: 'prompt';
  message: string;
  defaultValue: string;
  resolve: (v: string | null) => void;
}

type DialogState = ConfirmState | PromptState | null;

interface DialogContextValue {
  showConfirm: (message: string) => Promise<boolean>;
  showPrompt: (message: string, defaultValue?: string) => Promise<string | null>;
}

const DialogContext = createContext<DialogContextValue>({
  showConfirm: () => Promise.resolve(false),
  showPrompt: () => Promise.resolve(null),
});

export function useDialog() {
  return useContext(DialogContext);
}

export default function DialogProvider({ children }: { children: ReactNode }) {
  const [dialog, setDialog] = useState<DialogState>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const t = useTranslations('dialog');

  const showConfirm = useCallback((message: string): Promise<boolean> => {
    return new Promise((resolve) => {
      setDialog({ type: 'confirm', message, resolve });
    });
  }, []);

  const showPrompt = useCallback(
    (message: string, defaultValue = ''): Promise<string | null> => {
      return new Promise((resolve) => {
        setDialog({ type: 'prompt', message, defaultValue, resolve });
      });
    },
    []
  );

  function close() {
    setDialog(null);
  }

  function handleConfirmOk() {
    if (dialog?.type === 'confirm') dialog.resolve(true);
    close();
  }

  function handleConfirmCancel() {
    if (dialog?.type === 'confirm') dialog.resolve(false);
    close();
  }

  function handlePromptOk() {
    if (dialog?.type === 'prompt') {
      dialog.resolve(inputRef.current?.value ?? null);
    }
    close();
  }

  function handlePromptCancel() {
    if (dialog?.type === 'prompt') dialog.resolve(null);
    close();
  }

  return (
    <DialogContext.Provider value={{ showConfirm, showPrompt }}>
      {children}
      {dialog && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 p-4">
          <div
            className="w-full max-w-sm rounded-xl bg-white p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="mb-4 text-sm text-gray-700 whitespace-pre-wrap">{dialog.message}</p>

            {dialog.type === 'prompt' && (
              <input
                ref={inputRef}
                type="text"
                defaultValue={dialog.defaultValue}
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handlePromptOk();
                  if (e.key === 'Escape') handlePromptCancel();
                }}
                className="mb-4 w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            )}

            <div className="flex justify-end gap-2">
              <button
                onClick={dialog.type === 'confirm' ? handleConfirmCancel : handlePromptCancel}
                className="rounded-lg border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
              >
                {t('cancel')}
              </button>
              <button
                onClick={dialog.type === 'confirm' ? handleConfirmOk : handlePromptOk}
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
              >
                {t('confirm')}
              </button>
            </div>
          </div>
        </div>
      )}
    </DialogContext.Provider>
  );
}
