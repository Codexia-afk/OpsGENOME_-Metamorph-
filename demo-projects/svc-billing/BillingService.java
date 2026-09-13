package com.example.billing;

class InvoiceProcessingException extends RuntimeException {
    public InvoiceProcessingException(String message, Throwable cause) {
        super(message, cause);
    }
}

public class BillingService {
    public static void main(String[] args) {
        BillingService service = new BillingService();
        service.processBillingRun();
    }

    public void processBillingRun() {
        try {
            generateMonthlyStatement("CUST-9842");
        } catch (Exception e) {
            throw new InvoiceProcessingException("Failed to generate monthly billing statement for customer CUST-9842", e);
        }
    }

    private void generateMonthlyStatement(String customerId) {
        calculateTaxAmount(null, 250.00);
    }

    private double calculateTaxAmount(String jurisdictionCode, double subtotal) {
        // Line 29: Throws NullPointerException when invoking trim() on null jurisdictionCode
        if (jurisdictionCode.trim().equalsIgnoreCase("EU")) {
            return subtotal * 0.20;
        }
        return subtotal * 0.08;
    }
}
