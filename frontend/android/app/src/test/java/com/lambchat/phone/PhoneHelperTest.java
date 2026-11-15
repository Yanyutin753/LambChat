package com.lambchat.phone;
import org.junit.Test;
import static org.junit.Assert.*;
import java.io.BufferedReader;
import java.io.StringReader;

public class PhoneHelperTest {
    @Test public void rejectsOversizedAndTruncatedProtocolFrames() {
        assertThrows(IllegalStateException.class, () -> PhoneHelper.INSTANCE.boundedLine(new BufferedReader(new StringReader("12345\n")), 4));
        assertThrows(IllegalStateException.class, () -> PhoneHelper.INSTANCE.boundedLine(new BufferedReader(new StringReader("123")), 4));
    }
    @Test public void acceptsExactLimitAndCleanEof() {
        assertEquals("1234", PhoneHelper.INSTANCE.boundedLine(new BufferedReader(new StringReader("1234\n")), 4));
        assertNull(PhoneHelper.INSTANCE.boundedLine(new BufferedReader(new StringReader("")), 4));
    }
}
