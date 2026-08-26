/**
 * 消息列表使用 Virtuoso 的 firstItemIndex 反向无限滚动模式时，
 * Virtuoso 的索引语义是不对称的：
 *
 * - itemContent / rangeChanged 上报的是 firstItemIndex 起算的绝对索引
 *   （原始索引 + firstItemIndex）；
 * - scrollToIndex 接收的却是原始数据索引（0..n-1），越界索引会被钳制到
 *   [0, totalCount-1]——如果在这里加上 firstItemIndex，任何调用都会被钳到
 *   最后一条并滚到底部。
 *
 * 消息大纲、时间轴、外部导航等都按数据索引工作：
 * - 读取 rangeChanged 时用 translateVirtuosoRange 换回数据索引；
 * - 调用 scrollToIndex 时数据索引原样透传（wrapVirtuosoHandleForDataIndices）。
 */

import type { ListRange, VirtuosoHandle } from "react-virtuoso";

/** Virtuoso 绝对索引 → 消息数据索引 */
export function toDataIndex(
  absoluteIndex: number,
  firstItemIndex: number,
): number {
  return absoluteIndex - firstItemIndex;
}

/** 把 Virtuoso 上报的可视区范围换算回数据索引 */
export function translateVirtuosoRange(
  range: ListRange,
  firstItemIndex: number,
): ListRange {
  return {
    startIndex: Math.max(0, toDataIndex(range.startIndex, firstItemIndex)),
    endIndex: Math.max(0, toDataIndex(range.endIndex, firstItemIndex)),
  };
}

/**
 * 包装 VirtuosoHandle：调用方继续传数据索引。scrollToIndex 原生就期望
 * 数据索引，因此这里只做透传；保留这一层是为了把索引语义集中在一处。
 */
export function wrapVirtuosoHandleForDataIndices(
  handle: VirtuosoHandle,
): VirtuosoHandle {
  return { ...handle };
}
