import { useState, type ChangeEvent } from "react";
import { Lock, Eye, EyeOff } from "lucide-react";
import { useTranslation } from "react-i18next";

interface PasswordInputProps {
  value: string;
  onChange: (e: ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string;
  autoComplete?: string;
  className?: string;
  showPasswordLabel?: string;
  hidePasswordLabel?: string;
}

export function PasswordInput({
  value,
  onChange,
  placeholder,
  autoComplete,
  className = "",
  showPasswordLabel,
  hidePasswordLabel,
}: PasswordInputProps) {
  const { t } = useTranslation();
  const showLabel = showPasswordLabel ?? t("passwordInput.showPassword");
  const hideLabel = hidePasswordLabel ?? t("passwordInput.hidePassword");
  const [visible, setVisible] = useState(false);

  return (
    <div className="relative [&_::-ms-reveal]:hidden [&_::-webkit-credentials-auto-fill-button]:hidden">
      <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-stone-400 dark:text-stone-500 sm:pl-3.5">
        <Lock size={16} />
      </div>
      <input
        type={visible ? "text" : "password"}
        value={value}
        onChange={onChange}
        className={`auth-input w-full rounded-xl py-2.5 pl-10 pr-10 text-sm transition-all sm:py-3 sm:pl-11 sm:pr-4 ${className}`}
        placeholder={placeholder}
        autoComplete={autoComplete}
      />
      <button
        type="button"
        onClick={() => setVisible(!visible)}
        className="absolute inset-y-0 right-0 flex items-center rounded-r-xl pr-3 text-stone-400 transition-colors hover:text-stone-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-stone-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:text-stone-500 dark:hover:text-stone-300 dark:focus-visible:ring-stone-500/70 dark:focus-visible:ring-offset-stone-950"
        aria-label={visible ? hideLabel : showLabel}
      >
        {visible ? <EyeOff size={15} /> : <Eye size={15} />}
      </button>
    </div>
  );
}
