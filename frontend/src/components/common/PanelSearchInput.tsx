import {
  type ComponentType,
  forwardRef,
  type ReactNode,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type CompositionEvent,
  type FocusEvent,
  type InputHTMLAttributes,
} from "react";

type PanelSearchInputComponentProps = InputHTMLAttributes<HTMLInputElement> & {
  leadingIcon?: ReactNode;
  trailingSlot?: ReactNode;
  error?: boolean;
};

type PanelSearchInputProps = Omit<
  PanelSearchInputComponentProps,
  "onChange" | "value"
> & {
  as?: "input" | ComponentType<PanelSearchInputComponentProps>;
  value?: string;
  onValueChange: (value: string) => void;
};

export const PanelSearchInput = forwardRef<
  HTMLInputElement,
  PanelSearchInputProps
>(function PanelSearchInput(
  {
    value = "",
    onValueChange,
    as: InputComponent = "input",
    onFocus,
    onBlur,
    onCompositionStart,
    onCompositionEnd,
    ...props
  },
  ref,
) {
  const [draftValue, setDraftValue] = useState(value);
  const isEditingRef = useRef(false);

  useEffect(() => {
    if (!isEditingRef.current) {
      setDraftValue(value);
    }
  }, [value]);

  const handleChange = (event: ChangeEvent<HTMLInputElement>) => {
    const nextValue = event.currentTarget.value;
    setDraftValue(nextValue);
    onValueChange(nextValue);
  };

  const handleFocus = (event: FocusEvent<HTMLInputElement>) => {
    isEditingRef.current = true;
    onFocus?.(event);
  };

  const handleBlur = (event: FocusEvent<HTMLInputElement>) => {
    isEditingRef.current = false;
    if (draftValue !== value) {
      onValueChange(draftValue);
    }
    onBlur?.(event);
  };

  const handleCompositionStart = (
    event: CompositionEvent<HTMLInputElement>,
  ) => {
    isEditingRef.current = true;
    onCompositionStart?.(event);
  };

  const handleCompositionEnd = (event: CompositionEvent<HTMLInputElement>) => {
    const nextValue = event.currentTarget.value;
    setDraftValue(nextValue);
    onValueChange(nextValue);
    onCompositionEnd?.(event);
  };

  return (
    <InputComponent
      {...props}
      ref={ref}
      value={draftValue}
      onChange={handleChange}
      onFocus={handleFocus}
      onBlur={handleBlur}
      onCompositionStart={handleCompositionStart}
      onCompositionEnd={handleCompositionEnd}
    />
  );
});

export default PanelSearchInput;
