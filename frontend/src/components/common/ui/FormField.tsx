import {
  Children,
  cloneElement,
  isValidElement,
  useId,
  type ReactNode,
} from "react";
import { Input } from "./Input";
import { Textarea } from "./Textarea";

export interface FormFieldProps {
  label?: ReactNode;
  required?: boolean;
  hint?: ReactNode;
  error?: ReactNode;
  htmlFor?: string;
  className?: string;
  children: ReactNode;
}

function cx(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

export function FormField({
  label,
  required = false,
  hint,
  error,
  htmlFor,
  className,
  children,
}: FormFieldProps) {
  const generatedId = useId();
  const nodes = Children.toArray(children);
  const controlIndex = nodes.findIndex(
    (child) =>
      isValidElement(child) &&
      (child.type === Input ||
        child.type === Textarea ||
        child.type === "input" ||
        child.type === "textarea" ||
        child.type === "select"),
  );
  const control = nodes[controlIndex];
  const controlProps = isValidElement<{
    id?: string;
    "aria-describedby"?: string;
    "aria-invalid"?: boolean | "true" | "false";
  }>(control)
    ? control.props
    : undefined;
  const controlId = htmlFor ?? controlProps?.id ?? generatedId;
  const feedbackId = `${generatedId}-feedback`;
  return (
    <div className={cx("ui-field", className)}>
      {label && (
        <label
          className="ui-field__label"
          htmlFor={controlIndex >= 0 ? controlId : htmlFor}
        >
          {label}
          {required && <span className="ui-field__required">*</span>}
        </label>
      )}
      {nodes.map((child, index) =>
        index === controlIndex && isValidElement(child)
          ? cloneElement(child as React.ReactElement<Record<string, unknown>>, {
              id: controlId,
              "aria-describedby":
                cx(
                  controlProps?.["aria-describedby"],
                  Boolean(error || hint) && feedbackId,
                ) || undefined,
              ...(error ? { "aria-invalid": true } : {}),
            })
          : child,
      )}
      {error ? (
        <p id={feedbackId} role="alert" className="ui-field__error">
          {error}
        </p>
      ) : hint ? (
        <p id={feedbackId} className="ui-field__hint">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
