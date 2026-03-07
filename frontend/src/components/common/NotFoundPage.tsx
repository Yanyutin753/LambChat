import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { usePageTitle } from "../../hooks/usePageTitle";

export function NotFoundPage() {
  usePageTitle("404");
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <div className="flex h-screen w-full flex-col items-center justify-center bg-white dark:bg-stone-900 px-4">
      <div className="flex flex-col items-center max-w-md text-center">
        {/* Title */}
        <h1 className="text-2xl font-semibold text-gray-900 dark:text-stone-100 mb-2">
          {t("errors.pageNotFound")}
        </h1>

        {/* Description */}
        <p className="text-gray-500 dark:text-stone-400 mb-8 leading-relaxed">
          {t("errors.pageNotFoundDesc")}
        </p>

        {/* Button */}
        <button
          onClick={() => navigate("/chat")}
          className="inline-flex items-center gap-2 px-6 py-4 bg-gray-900 dark:bg-stone-100 hover:bg-gray-800 dark:hover:bg-stone-200 text-white dark:text-stone-900 text-sm font-medium rounded-full transition-colors"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
            className="size-5"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"
            />
          </svg>
          {t("errors.backToHome")}
        </button>
      </div>
    </div>
  );
}
