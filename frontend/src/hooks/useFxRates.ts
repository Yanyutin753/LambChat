// USD → 本地货币换算汇率（模块级缓存，30 分钟 TTL，失败回落 USD）
import { useEffect, useState } from "react";
import { getFxRates } from "../services/api/pricing";
import type { FxRatesDoc } from "../utils/currency";

export function useFxRates(): FxRatesDoc | null {
  const [rates, setRates] = useState<FxRatesDoc | null>(null);

  useEffect(() => {
    let alive = true;
    getFxRates()
      .then((doc) => {
        if (alive && doc) {
          setRates({ base: doc.base, rates: doc.rates, synced_at: doc.synced_at });
        }
      })
      .catch(() => null);
    return () => {
      alive = false;
    };
  }, []);

  return rates;
}
